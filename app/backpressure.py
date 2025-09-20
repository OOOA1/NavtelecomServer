"""Backpressure management and queue protection."""
import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import deque
import structlog

logger = structlog.get_logger()


@dataclass
class QueueStats:
    """Queue statistics."""
    size: int
    max_size: int
    dropped_count: int
    last_drop_time: float
    is_overloaded: bool


class BackpressureManager:
    """Manages backpressure and queue protection."""
    
    def __init__(self, max_queue_size: int = 10000, drop_threshold: float = 0.8):
        self.max_queue_size = max_queue_size
        self.drop_threshold = drop_threshold
        self.drop_threshold_size = int(max_queue_size * drop_threshold)
        self.queues: Dict[str, asyncio.Queue] = {}
        self.queue_stats: Dict[str, QueueStats] = {}
        self.persist_only_mode = False
        self.last_stats_update = time.time()
    
    def get_or_create_queue(self, queue_name: str) -> asyncio.Queue:
        """Get or create a queue with backpressure management."""
        if queue_name not in self.queues:
            self.queues[queue_name] = asyncio.Queue(maxsize=self.max_queue_size)
            self.queue_stats[queue_name] = QueueStats(
                size=0,
                max_size=self.max_queue_size,
                dropped_count=0,
                last_drop_time=0.0,
                is_overloaded=False
            )
        
        return self.queues[queue_name]
    
    async def put_with_backpressure(self, queue_name: str, item: Any, 
                                  priority: str = "normal") -> bool:
        """Put item in queue with backpressure protection."""
        queue = self.get_or_create_queue(queue_name)
        stats = self.queue_stats[queue_name]
        
        # Check if queue is overloaded
        if queue.qsize() >= self.drop_threshold_size:
            stats.is_overloaded = True
            
            # Drop low priority items
            if priority == "low":
                stats.dropped_count += 1
                stats.last_drop_time = time.time()
                
                logger.warning(
                    "item_dropped",
                    queue_name=queue_name,
                    priority=priority,
                    queue_size=queue.qsize(),
                    dropped_count=stats.dropped_count
                )
                return False
            
            # For high priority, try to make space
            if priority == "high":
                try:
                    # Remove one low priority item if possible
                    await asyncio.wait_for(queue.get(), timeout=0.1)
                    stats.dropped_count += 1
                    stats.last_drop_time = time.time()
                except asyncio.TimeoutError:
                    pass
        
        # Try to put item in queue
        try:
            await asyncio.wait_for(queue.put(item), timeout=0.1)
            stats.size = queue.qsize()
            stats.is_overloaded = False
            return True
        except asyncio.TimeoutError:
            # Queue is full, drop item
            stats.dropped_count += 1
            stats.last_drop_time = time.time()
            
            logger.error(
                "queue_full_drop",
                queue_name=queue_name,
                priority=priority,
                queue_size=queue.qsize(),
                dropped_count=stats.dropped_count
            )
            return False
    
    async def get_with_timeout(self, queue_name: str, timeout: float = 1.0) -> Optional[Any]:
        """Get item from queue with timeout."""
        queue = self.get_or_create_queue(queue_name)
        stats = self.queue_stats[queue_name]
        
        try:
            item = await asyncio.wait_for(queue.get(), timeout=timeout)
            stats.size = queue.qsize()
            return item
        except asyncio.TimeoutError:
            return None
    
    def get_queue_stats(self, queue_name: str) -> Optional[QueueStats]:
        """Get queue statistics."""
        if queue_name in self.queue_stats:
            stats = self.queue_stats[queue_name]
            if queue_name in self.queues:
                stats.size = self.queues[queue_name].qsize()
            return stats
        return None
    
    def get_all_stats(self) -> Dict[str, QueueStats]:
        """Get all queue statistics."""
        for queue_name in self.queue_stats:
            if queue_name in self.queues:
                self.queue_stats[queue_name].size = self.queues[queue_name].qsize()
        return dict(self.queue_stats)
    
    def is_system_overloaded(self) -> bool:
        """Check if system is overloaded."""
        total_size = sum(stats.size for stats in self.queue_stats.values())
        total_max = sum(stats.max_size for stats in self.queue_stats.values())
        
        if total_max == 0:
            return False
        
        overload_ratio = total_size / total_max
        return overload_ratio >= self.drop_threshold
    
    def enable_persist_only_mode(self):
        """Enable persist-only mode (save raw data, skip processing)."""
        self.persist_only_mode = True
        logger.warning("persist_only_mode_enabled")
    
    def disable_persist_only_mode(self):
        """Disable persist-only mode."""
        self.persist_only_mode = False
        logger.info("persist_only_mode_disabled")
    
    def should_persist_only(self) -> bool:
        """Check if we should only persist data (skip processing)."""
        return self.persist_only_mode or self.is_system_overloaded()


class RateLimiter:
    """Rate limiter for devices and connections."""
    
    def __init__(self, max_requests_per_minute: int = 1000, max_burst: int = 100):
        self.max_requests_per_minute = max_requests_per_minute
        self.max_burst = max_burst
        self.device_rates: Dict[str, deque] = {}
        self.connection_rates: Dict[str, deque] = {}
        self.last_cleanup = time.time()
    
    def is_allowed(self, device_id: str = None, connection_id: str = None) -> bool:
        """Check if request is allowed."""
        current_time = time.time()
        
        # Cleanup old entries periodically
        if current_time - self.last_cleanup > 60.0:
            self._cleanup_old_entries(current_time)
            self.last_cleanup = current_time
        
        # Check device rate limit
        if device_id:
            if not self._check_rate_limit(device_id, self.device_rates, current_time):
                logger.warning(
                    "device_rate_limit_exceeded",
                    device_id=device_id,
                    max_requests_per_minute=self.max_requests_per_minute
                )
                return False
        
        # Check connection rate limit
        if connection_id:
            if not self._check_rate_limit(connection_id, self.connection_rates, current_time):
                logger.warning(
                    "connection_rate_limit_exceeded",
                    connection_id=connection_id,
                    max_requests_per_minute=self.max_requests_per_minute
                )
                return False
        
        return True
    
    def _check_rate_limit(self, key: str, rate_dict: Dict[str, deque], current_time: float) -> bool:
        """Check rate limit for a specific key."""
        if key not in rate_dict:
            rate_dict[key] = deque()
        
        timestamps = rate_dict[key]
        
        # Remove timestamps older than 1 minute
        while timestamps and current_time - timestamps[0] > 60.0:
            timestamps.popleft()
        
        # Check if we're within limits
        if len(timestamps) >= self.max_requests_per_minute:
            return False
        
        # Add current timestamp
        timestamps.append(current_time)
        return True
    
    def _cleanup_old_entries(self, current_time: float):
        """Cleanup old rate limit entries."""
        for key, timestamps in list(self.device_rates.items()):
            while timestamps and current_time - timestamps[0] > 60.0:
                timestamps.popleft()
            if not timestamps:
                del self.device_rates[key]
        
        for key, timestamps in list(self.connection_rates.items()):
            while timestamps and current_time - timestamps[0] > 60.0:
                timestamps.popleft()
            if not timestamps:
                del self.connection_rates[key]


# Global instances
backpressure_manager = BackpressureManager()
rate_limiter = RateLimiter()
