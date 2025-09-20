"""
Tenant-aware load balancing and throttling system.
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import structlog
from collections import defaultdict, deque

from app.tenant_manager import tenant_manager
from app.backpressure import BackpressureManager, RateLimiter

logger = structlog.get_logger()


class TenantLoadBalancer:
    """Manages load balancing and throttling per tenant."""
    
    def __init__(self):
        self.tenant_queues: Dict[str, asyncio.Queue] = {}
        self.tenant_workers: Dict[str, List[asyncio.Task]] = {}
        self.tenant_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "frames_processed": 0,
            "frames_dropped": 0,
            "queue_size": 0,
            "processing_time": 0.0,
            "last_activity": None
        })
        
        # Configuration
        self.max_workers_per_tenant = 5
        self.max_queue_size_per_tenant = 10000
        self.worker_timeout_seconds = 30
        self.monitoring_interval_seconds = 60
        
        # Rate limiters per tenant
        self.tenant_rate_limiters: Dict[str, RateLimiter] = {}
        
        # Backpressure managers per tenant
        self.tenant_backpressure: Dict[str, BackpressureManager] = {}
        
        self.monitoring_task: Optional[asyncio.Task] = None
        
        logger.info("tenant_load_balancer_initialized")
    
    async def initialize_tenant(self, tenant_id: str):
        """Initialize tenant-specific resources."""
        if tenant_id not in self.tenant_queues:
            # Create tenant queue
            self.tenant_queues[tenant_id] = asyncio.Queue(maxsize=self.max_queue_size_per_tenant)
            
            # Create tenant rate limiter
            self.tenant_rate_limiters[tenant_id] = RateLimiter(
                requests_per_minute=1000,  # Default, will be updated from tenant limits
                burst_size=100
            )
            
            # Create tenant backpressure manager
            self.tenant_backpressure[tenant_id] = BackpressureManager(
                max_queue_size=self.max_queue_size_per_tenant,
                persist_only_threshold=0.8
            )
            
            # Start tenant workers
            await self._start_tenant_workers(tenant_id)
            
            logger.info("tenant_initialized", tenant_id=tenant_id)
    
    async def _start_tenant_workers(self, tenant_id: str):
        """Start workers for a tenant."""
        if tenant_id in self.tenant_workers:
            return  # Already started
        
        self.tenant_workers[tenant_id] = []
        
        # Start workers
        for i in range(self.max_workers_per_tenant):
            worker = asyncio.create_task(self._tenant_worker(tenant_id, i))
            self.tenant_workers[tenant_id].append(worker)
        
        logger.info("tenant_workers_started", tenant_id=tenant_id, count=self.max_workers_per_tenant)
    
    async def _tenant_worker(self, tenant_id: str, worker_id: int):
        """Worker task for processing tenant data."""
        logger.info("tenant_worker_started", tenant_id=tenant_id, worker_id=worker_id)
        
        try:
            while True:
                try:
                    # Get item from queue with timeout
                    item = await asyncio.wait_for(
                        self.tenant_queues[tenant_id].get(),
                        timeout=self.worker_timeout_seconds
                    )
                    
                    # Process item
                    start_time = time.time()
                    await self._process_tenant_item(tenant_id, item)
                    processing_time = time.time() - start_time
                    
                    # Update metrics
                    self.tenant_metrics[tenant_id]["frames_processed"] += 1
                    self.tenant_metrics[tenant_id]["processing_time"] += processing_time
                    self.tenant_metrics[tenant_id]["last_activity"] = datetime.now(timezone.utc)
                    
                    # Mark task as done
                    self.tenant_queues[tenant_id].task_done()
                    
                except asyncio.TimeoutError:
                    # No work to do, continue
                    continue
                except Exception as e:
                    logger.error("tenant_worker_error", tenant_id=tenant_id, worker_id=worker_id, error=str(e))
                    
        except asyncio.CancelledError:
            logger.info("tenant_worker_cancelled", tenant_id=tenant_id, worker_id=worker_id)
        except Exception as e:
            logger.error("tenant_worker_fatal_error", tenant_id=tenant_id, worker_id=worker_id, error=str(e))
    
    async def _process_tenant_item(self, tenant_id: str, item: Dict[str, Any]):
        """Process a single item for a tenant."""
        try:
            # Set tenant context
            from app.db import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                await tenant_manager.set_tenant_context(session, tenant_id)
                
                # Process based on item type
                item_type = item.get("type")
                
                if item_type == "raw_frame":
                    await self._process_raw_frame(session, tenant_id, item)
                elif item_type == "can_frame":
                    await self._process_can_frame(session, tenant_id, item)
                elif item_type == "telemetry":
                    await self._process_telemetry(session, tenant_id, item)
                else:
                    logger.warning("unknown_item_type", tenant_id=tenant_id, item_type=item_type)
                
        except Exception as e:
            logger.error("tenant_item_processing_error", tenant_id=tenant_id, error=str(e))
    
    async def _process_raw_frame(self, session, tenant_id: str, item: Dict[str, Any]):
        """Process raw frame for tenant."""
        from app.models import save_raw_frame
        
        # Check quota
        if not await tenant_manager.check_quota(tenant_id, "max_frames_per_minute", 1):
            logger.warning("tenant_quota_exceeded", tenant_id=tenant_id, quota_type="max_frames_per_minute")
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return
        
        # Save frame
        await save_raw_frame(
            session=session,
            device_id=item["device_id"],
            payload=item["payload"],
            received_at=item["received_at"],
            tenant_id=tenant_id
        )
        
        # Update quota
        await tenant_manager.update_quota(tenant_id, "max_frames_per_minute", 1)
    
    async def _process_can_frame(self, session, tenant_id: str, item: Dict[str, Any]):
        """Process CAN frame for tenant."""
        from app.models import save_can_raw_frame
        
        # Check quota
        if not await tenant_manager.check_quota(tenant_id, "max_can_frames_per_minute", 1):
            logger.warning("tenant_quota_exceeded", tenant_id=tenant_id, quota_type="max_can_frames_per_minute")
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return
        
        # Save CAN frame
        await save_can_raw_frame(
            session=session,
            device_id=item["device_id"],
            can_id=item["can_id"],
            payload=item["payload"],
            recv_time=item["recv_time"],
            tenant_id=tenant_id
        )
        
        # Update quota
        await tenant_manager.update_quota(tenant_id, "max_can_frames_per_minute", 1)
    
    async def _process_telemetry(self, session, tenant_id: str, item: Dict[str, Any]):
        """Process telemetry for tenant."""
        from app.models import save_telemetry
        
        # Check quota
        if not await tenant_manager.check_quota(tenant_id, "max_frames_per_minute", 1):
            logger.warning("tenant_quota_exceeded", tenant_id=tenant_id, quota_type="max_frames_per_minute")
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return
        
        # Save telemetry
        await save_telemetry(
            session=session,
            device_id=item["device_id"],
            data=item["data"],
            received_at=item["received_at"],
            tenant_id=tenant_id
        )
        
        # Update quota
        await tenant_manager.update_quota(tenant_id, "max_frames_per_minute", 1)
    
    async def add_item(self, tenant_id: str, item: Dict[str, Any]) -> bool:
        """Add item to tenant queue."""
        # Initialize tenant if needed
        if tenant_id not in self.tenant_queues:
            await self.initialize_tenant(tenant_id)
        
        # Check rate limiting
        if not self.tenant_rate_limiters[tenant_id].is_allowed(device_id=tenant_id):
            logger.warning("tenant_rate_limited", tenant_id=tenant_id)
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return False
        
        # Check backpressure
        if not self.tenant_backpressure[tenant_id].put(tenant_id, item, priority="normal"):
            logger.warning("tenant_backpressure_active", tenant_id=tenant_id)
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return False
        
        # Add to queue
        try:
            self.tenant_queues[tenant_id].put_nowait(item)
            self.tenant_metrics[tenant_id]["queue_size"] = self.tenant_queues[tenant_id].qsize()
            return True
        except asyncio.QueueFull:
            logger.warning("tenant_queue_full", tenant_id=tenant_id)
            self.tenant_metrics[tenant_id]["frames_dropped"] += 1
            return False
    
    async def get_tenant_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant processing status."""
        if tenant_id not in self.tenant_queues:
            return {"status": "not_initialized"}
        
        metrics = self.tenant_metrics[tenant_id]
        queue_size = self.tenant_queues[tenant_id].qsize()
        
        return {
            "status": "active",
            "queue_size": queue_size,
            "frames_processed": metrics["frames_processed"],
            "frames_dropped": metrics["frames_dropped"],
            "processing_time": metrics["processing_time"],
            "last_activity": metrics["last_activity"],
            "workers_count": len(self.tenant_workers.get(tenant_id, [])),
            "rate_limiter_status": "active" if self.tenant_rate_limiters[tenant_id] else "inactive",
            "backpressure_status": "active" if self.tenant_backpressure[tenant_id] else "inactive"
        }
    
    async def get_all_tenant_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all tenants."""
        status = {}
        for tenant_id in self.tenant_queues.keys():
            status[tenant_id] = await self.get_tenant_status(tenant_id)
        return status
    
    async def update_tenant_limits(self, tenant_id: str, limits: Dict[str, Any]):
        """Update tenant rate limits."""
        if tenant_id in self.tenant_rate_limiters:
            # Update rate limiter
            rate_limiter = self.tenant_rate_limiters[tenant_id]
            rate_limiter.requests_per_minute = limits.get("max_frames_per_minute", 1000)
            rate_limiter.burst_size = limits.get("max_frames_per_minute", 1000) // 10
            
            logger.info("tenant_limits_updated", tenant_id=tenant_id, limits=limits)
    
    async def _monitor_tenant_health(self):
        """Background task to monitor tenant health."""
        while True:
            try:
                for tenant_id in list(self.tenant_queues.keys()):
                    status = await self.get_tenant_status(tenant_id)
                    
                    # Check for stuck queues
                    if status["queue_size"] > self.max_queue_size_per_tenant * 0.8:
                        logger.warning("tenant_queue_high", tenant_id=tenant_id, queue_size=status["queue_size"])
                        
                        # Send alert
                        from app.alerts import alert_manager, AlertSeverity
                        alert_manager.raise_alert(
                            name=f"TenantQueueHigh_{tenant_id}",
                            severity=AlertSeverity.WARNING,
                            message=f"Tenant {tenant_id} queue is high: {status['queue_size']} items",
                            labels={"tenant_id": tenant_id},
                            value=status["queue_size"],
                            threshold=self.max_queue_size_per_tenant * 0.8
                        )
                    
                    # Check for inactive tenants
                    if status["last_activity"]:
                        inactive_time = datetime.now(timezone.utc) - status["last_activity"]
                        if inactive_time > timedelta(hours=1):
                            logger.info("tenant_inactive", tenant_id=tenant_id, inactive_time=inactive_time)
                
                # Clean up inactive tenants
                await self._cleanup_inactive_tenants()
                
            except Exception as e:
                logger.error("tenant_health_monitoring_error", error=str(e))
            
            # Monitor every minute
            await asyncio.sleep(self.monitoring_interval_seconds)
    
    async def _cleanup_inactive_tenants(self):
        """Clean up inactive tenant resources."""
        inactive_tenants = []
        
        for tenant_id, metrics in self.tenant_metrics.items():
            if metrics["last_activity"]:
                inactive_time = datetime.now(timezone.utc) - metrics["last_activity"]
                if inactive_time > timedelta(hours=24):
                    inactive_tenants.append(tenant_id)
        
        for tenant_id in inactive_tenants:
            await self._cleanup_tenant(tenant_id)
            logger.info("inactive_tenant_cleaned", tenant_id=tenant_id)
    
    async def _cleanup_tenant(self, tenant_id: str):
        """Clean up tenant resources."""
        # Stop workers
        if tenant_id in self.tenant_workers:
            for worker in self.tenant_workers[tenant_id]:
                worker.cancel()
            self.tenant_workers[tenant_id] = []
        
        # Clear queue
        if tenant_id in self.tenant_queues:
            while not self.tenant_queues[tenant_id].empty():
                try:
                    self.tenant_queues[tenant_id].get_nowait()
                except asyncio.QueueEmpty:
                    break
        
        # Remove from tracking
        if tenant_id in self.tenant_queues:
            del self.tenant_queues[tenant_id]
        if tenant_id in self.tenant_rate_limiters:
            del self.tenant_rate_limiters[tenant_id]
        if tenant_id in self.tenant_backpressure:
            del self.tenant_backpressure[tenant_id]
        if tenant_id in self.tenant_metrics:
            del self.tenant_metrics[tenant_id]
    
    async def start_monitoring(self):
        """Start tenant monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_tenant_health())
            logger.info("tenant_load_balancer_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop tenant monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("tenant_load_balancer_monitoring_stopped")
            self.monitoring_task = None
        
        # Clean up all tenants
        for tenant_id in list(self.tenant_queues.keys()):
            await self._cleanup_tenant(tenant_id)


tenant_load_balancer = TenantLoadBalancer()

