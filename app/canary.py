"""
Canary deployment and shadow traffic system.
"""
import asyncio
import random
import hashlib
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import structlog

logger = structlog.get_logger()

class CanaryStrategy(Enum):
    """Canary deployment strategies."""
    PERCENTAGE = "percentage"  # X% of devices
    DEVICE_LIST = "device_list"  # Specific device IDs
    HASH_BASED = "hash_based"  # Hash-based selection
    RANDOM = "random"  # Random selection

@dataclass
class CanaryConfig:
    """Canary deployment configuration."""
    name: str
    strategy: CanaryStrategy
    percentage: float = 0.0  # 0.0 to 1.0
    device_ids: Set[str] = None
    enabled: bool = False
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class ShadowTrafficConfig:
    """Shadow traffic configuration."""
    name: str
    target_url: str
    percentage: float = 0.0  # 0.0 to 1.0
    device_ids: Set[str] = None
    enabled: bool = False
    timeout_ms: int = 5000
    retry_count: int = 3
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class CanaryMetrics:
    """Canary deployment metrics."""
    canary_name: str
    device_id: str
    timestamp: datetime
    success: bool
    latency_ms: float
    error_message: Optional[str] = None
    feature_version: Optional[str] = None

class CanaryManager:
    """Manages canary deployments and shadow traffic."""
    
    def __init__(self):
        self.canary_configs: Dict[str, CanaryConfig] = {}
        self.shadow_configs: Dict[str, ShadowTrafficConfig] = {}
        self.canary_metrics: List[CanaryMetrics] = []
        self._running = False
        self._monitoring_task = None
        
        # Feature flags
        self.feature_flags: Dict[str, bool] = {
            "new_can_parser": False,
            "enhanced_tp_assembly": False,
            "improved_backpressure": False,
            "new_metrics": False
        }
        
        # Default canary configs
        self._initialize_default_configs()
    
    async def start(self):
        """Start canary manager."""
        if not self._running:
            self._running = True
            self._monitoring_task = asyncio.create_task(self._monitor_canaries())
            logger.info("canary_manager_started")
    
    async def stop(self):
        """Stop canary manager."""
        if self._running:
            self._running = False
            if self._monitoring_task:
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            logger.info("canary_manager_stopped")
    
    def _initialize_default_configs(self):
        """Initialize default canary configurations."""
        # New CAN parser canary
        self.canary_configs["new_can_parser"] = CanaryConfig(
            name="new_can_parser",
            strategy=CanaryStrategy.PERCENTAGE,
            percentage=0.1,  # 10% of devices
            enabled=False,
            created_at=datetime.now(timezone.utc)
        )
        
        # Enhanced TP assembly canary
        self.canary_configs["enhanced_tp_assembly"] = CanaryConfig(
            name="enhanced_tp_assembly",
            strategy=CanaryStrategy.DEVICE_LIST,
            device_ids=set(),
            enabled=False,
            created_at=datetime.now(timezone.utc)
        )
        
        # Shadow traffic to external API
        self.shadow_configs["external_api"] = ShadowTrafficConfig(
            name="external_api",
            target_url="https://api.example.com/can-data",
            percentage=0.05,  # 5% of traffic
            enabled=False,
            created_at=datetime.now(timezone.utc)
        )
    
    def is_device_in_canary(self, device_id: str, canary_name: str) -> bool:
        """Check if device is in canary deployment."""
        if canary_name not in self.canary_configs:
            return False
        
        config = self.canary_configs[canary_name]
        if not config.enabled:
            return False
        
        if config.strategy == CanaryStrategy.PERCENTAGE:
            # Hash-based percentage selection
            device_hash = int(hashlib.md5(device_id.encode()).hexdigest(), 16)
            return (device_hash % 100) < (config.percentage * 100)
        
        elif config.strategy == CanaryStrategy.DEVICE_LIST:
            return device_id in config.device_ids
        
        elif config.strategy == CanaryStrategy.HASH_BASED:
            # Hash-based selection with consistent hashing
            device_hash = int(hashlib.md5(device_id.encode()).hexdigest(), 16)
            return (device_hash % 100) < (config.percentage * 100)
        
        elif config.strategy == CanaryStrategy.RANDOM:
            return random.random() < config.percentage
        
        return False
    
    def is_device_in_shadow(self, device_id: str, shadow_name: str) -> bool:
        """Check if device is in shadow traffic."""
        if shadow_name not in self.shadow_configs:
            return False
        
        config = self.shadow_configs[shadow_name]
        if not config.enabled:
            return False
        
        if config.device_ids:
            return device_id in config.device_ids
        
        # Percentage-based selection
        device_hash = int(hashlib.md5(device_id.encode()).hexdigest(), 16)
        return (device_hash % 100) < (config.percentage * 100)
    
    def get_feature_flag(self, feature_name: str, device_id: str) -> bool:
        """Get feature flag value for device."""
        if feature_name not in self.feature_flags:
            return False
        
        # Check if device is in canary for this feature
        if self.is_device_in_canary(device_id, feature_name):
            return True
        
        # Return global feature flag value
        return self.feature_flags[feature_name]
    
    async def create_canary_config(
        self,
        name: str,
        strategy: CanaryStrategy,
        percentage: float = 0.0,
        device_ids: Optional[Set[str]] = None,
        enabled: bool = False
    ) -> bool:
        """Create a new canary configuration."""
        try:
            config = CanaryConfig(
                name=name,
                strategy=strategy,
                percentage=percentage,
                device_ids=device_ids or set(),
                enabled=enabled,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            self.canary_configs[name] = config
            logger.info("canary_config_created", name=name, strategy=strategy.value)
            return True
            
        except Exception as e:
            logger.error("canary_config_create_error", name=name, error=str(e))
            return False
    
    async def update_canary_config(
        self,
        name: str,
        percentage: Optional[float] = None,
        device_ids: Optional[Set[str]] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """Update canary configuration."""
        if name not in self.canary_configs:
            return False
        
        try:
            config = self.canary_configs[name]
            
            if percentage is not None:
                config.percentage = percentage
            if device_ids is not None:
                config.device_ids = device_ids
            if enabled is not None:
                config.enabled = enabled
            
            config.updated_at = datetime.now(timezone.utc)
            
            logger.info("canary_config_updated", name=name)
            return True
            
        except Exception as e:
            logger.error("canary_config_update_error", name=name, error=str(e))
            return False
    
    async def create_shadow_config(
        self,
        name: str,
        target_url: str,
        percentage: float = 0.0,
        device_ids: Optional[Set[str]] = None,
        enabled: bool = False,
        timeout_ms: int = 5000,
        retry_count: int = 3
    ) -> bool:
        """Create a new shadow traffic configuration."""
        try:
            config = ShadowTrafficConfig(
                name=name,
                target_url=target_url,
                percentage=percentage,
                device_ids=device_ids or set(),
                enabled=enabled,
                timeout_ms=timeout_ms,
                retry_count=retry_count,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            self.shadow_configs[name] = config
            logger.info("shadow_config_created", name=name, target_url=target_url)
            return True
            
        except Exception as e:
            logger.error("shadow_config_create_error", name=name, error=str(e))
            return False
    
    async def send_shadow_traffic(
        self,
        shadow_name: str,
        device_id: str,
        data: Dict[str, Any]
    ) -> bool:
        """Send shadow traffic to external endpoint."""
        if shadow_name not in self.shadow_configs:
            return False
        
        config = self.shadow_configs[shadow_name]
        if not config.enabled:
            return False
        
        if not self.is_device_in_shadow(device_id, shadow_name):
            return False
        
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=config.timeout_ms / 1000) as client:
                response = await client.post(
                    config.target_url,
                    json={
                        "device_id": device_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data": data
                    }
                )
                
                success = response.status_code < 400
                
                # Record metrics
                self.canary_metrics.append(CanaryMetrics(
                    canary_name=shadow_name,
                    device_id=device_id,
                    timestamp=datetime.now(timezone.utc),
                    success=success,
                    latency_ms=response.elapsed.total_seconds() * 1000,
                    error_message=None if success else f"HTTP {response.status_code}"
                ))
                
                logger.debug(
                    "shadow_traffic_sent",
                    shadow_name=shadow_name,
                    device_id=device_id,
                    status_code=response.status_code,
                    latency_ms=response.elapsed.total_seconds() * 1000
                )
                
                return success
                
        except Exception as e:
            # Record error metrics
            self.canary_metrics.append(CanaryMetrics(
                canary_name=shadow_name,
                device_id=device_id,
                timestamp=datetime.now(timezone.utc),
                success=False,
                latency_ms=0.0,
                error_message=str(e)
            ))
            
            logger.error(
                "shadow_traffic_error",
                shadow_name=shadow_name,
                device_id=device_id,
                error=str(e)
            )
            return False
    
    def record_canary_metric(
        self,
        canary_name: str,
        device_id: str,
        success: bool,
        latency_ms: float,
        error_message: Optional[str] = None,
        feature_version: Optional[str] = None
    ):
        """Record canary deployment metrics."""
        metric = CanaryMetrics(
            canary_name=canary_name,
            device_id=device_id,
            timestamp=datetime.now(timezone.utc),
            success=success,
            latency_ms=latency_ms,
            error_message=error_message,
            feature_version=feature_version
        )
        
        self.canary_metrics.append(metric)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = datetime.now(timezone.utc).timestamp() - 86400
        self.canary_metrics = [
            m for m in self.canary_metrics 
            if m.timestamp.timestamp() > cutoff_time
        ]
    
    def get_canary_metrics(self, canary_name: Optional[str] = None, limit: int = 1000) -> List[CanaryMetrics]:
        """Get canary metrics."""
        metrics = self.canary_metrics
        
        if canary_name:
            metrics = [m for m in metrics if m.canary_name == canary_name]
        
        return metrics[-limit:]
    
    def get_canary_summary(self, canary_name: str) -> Dict[str, Any]:
        """Get canary deployment summary."""
        metrics = self.get_canary_metrics(canary_name)
        
        if not metrics:
            return {
                "canary_name": canary_name,
                "total_requests": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "error_count": 0
            }
        
        total_requests = len(metrics)
        successful_requests = sum(1 for m in metrics if m.success)
        success_rate = successful_requests / total_requests if total_requests > 0 else 0.0
        avg_latency = sum(m.latency_ms for m in metrics) / total_requests if total_requests > 0 else 0.0
        error_count = total_requests - successful_requests
        
        return {
            "canary_name": canary_name,
            "total_requests": total_requests,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "error_count": error_count,
            "recent_errors": [
                {
                    "device_id": m.device_id,
                    "timestamp": m.timestamp.isoformat(),
                    "error_message": m.error_message
                }
                for m in metrics[-10:] if not m.success
            ]
        }
    
    async def _monitor_canaries(self):
        """Monitor canary deployments."""
        while self._running:
            try:
                # Check canary health
                for canary_name in self.canary_configs.keys():
                    if self.canary_configs[canary_name].enabled:
                        summary = self.get_canary_summary(canary_name)
                        
                        # Alert if success rate is too low
                        if summary["total_requests"] > 100 and summary["success_rate"] < 0.95:
                            logger.warning(
                                "canary_low_success_rate",
                                canary_name=canary_name,
                                success_rate=summary["success_rate"],
                                total_requests=summary["total_requests"]
                            )
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("canary_monitoring_error", error=str(e))
                await asyncio.sleep(60)
    
    def list_canary_configs(self) -> Dict[str, CanaryConfig]:
        """List all canary configurations."""
        return self.canary_configs.copy()
    
    def list_shadow_configs(self) -> Dict[str, ShadowTrafficConfig]:
        """List all shadow traffic configurations."""
        return self.shadow_configs.copy()
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags."""
        return self.feature_flags.copy()
    
    def set_feature_flag(self, feature_name: str, enabled: bool) -> bool:
        """Set feature flag value."""
        if feature_name in self.feature_flags:
            self.feature_flags[feature_name] = enabled
            logger.info("feature_flag_updated", feature=feature_name, enabled=enabled)
            return True
        return False

# Global canary manager instance
canary_manager = CanaryManager()
