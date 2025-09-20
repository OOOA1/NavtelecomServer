"""Batch processing for database operations."""
import asyncio
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict
import structlog

logger = structlog.get_logger()


@dataclass
class BatchItem:
    """Item to be processed in batch."""
    operation: str
    data: Dict[str, Any]
    timestamp: float
    priority: str = "normal"


class BatchProcessor:
    """Batch processor for database operations."""
    
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.batches: Dict[str, List[BatchItem]] = defaultdict(list)
        self.last_flush = time.time()
        self.running = False
        self.flush_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start batch processor."""
        self.running = True
        self.flush_task = asyncio.create_task(self._flush_loop())
        logger.info("batch_processor_started")
    
    async def stop(self):
        """Stop batch processor."""
        self.running = False
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining batches
        await self._flush_all_batches()
        logger.info("batch_processor_stopped")
    
    async def add_item(self, batch_type: str, operation: str, data: Dict[str, Any], 
                      priority: str = "normal") -> bool:
        """Add item to batch."""
        item = BatchItem(
            operation=operation,
            data=data,
            timestamp=time.time(),
            priority=priority
        )
        
        self.batches[batch_type].append(item)
        
        # Check if batch is full
        if len(self.batches[batch_type]) >= self.batch_size:
            await self._flush_batch(batch_type)
            return True
        
        return False
    
    async def _flush_loop(self):
        """Main flush loop."""
        while self.running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_all_batches()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("flush_loop_error", error=str(e))
    
    async def _flush_all_batches(self):
        """Flush all batches."""
        for batch_type in list(self.batches.keys()):
            if self.batches[batch_type]:
                await self._flush_batch(batch_type)
    
    async def _flush_batch(self, batch_type: str):
        """Flush specific batch."""
        if not self.batches[batch_type]:
            return
        
        batch = self.batches[batch_type]
        self.batches[batch_type] = []
        
        try:
            if batch_type == "raw_frames":
                await self._flush_raw_frames_batch(batch)
            elif batch_type == "can_raw":
                await self._flush_can_raw_batch(batch)
            elif batch_type == "can_signals":
                await self._flush_can_signals_batch(batch)
            elif batch_type == "telemetry":
                await self._flush_telemetry_batch(batch)
            else:
                logger.warning("unknown_batch_type", batch_type=batch_type)
        
        except Exception as e:
            logger.error("batch_flush_error", batch_type=batch_type, error=str(e))
    
    async def _flush_raw_frames_batch(self, batch: List[BatchItem]):
        """Flush raw frames batch."""
        if not batch:
            return
        
        from app.models import save_raw_frame_batch
        
        batch_data = []
        for item in batch:
            batch_data.append(item.data)
        
        await save_raw_frame_batch(batch_data)
        
        logger.debug(
            "raw_frames_batch_flushed",
            count=len(batch_data)
        )
    
    async def _flush_can_raw_batch(self, batch: List[BatchItem]):
        """Flush CAN raw frames batch."""
        if not batch:
            return
        
        from app.models import save_can_raw_frame_batch
        
        batch_data = []
        for item in batch:
            batch_data.append(item.data)
        
        await save_can_raw_frame_batch(batch_data)
        
        logger.debug(
            "can_raw_batch_flushed",
            count=len(batch_data)
        )
    
    async def _flush_can_signals_batch(self, batch: List[BatchItem]):
        """Flush CAN signals batch."""
        if not batch:
            return
        
        from app.models import save_can_signal_batch
        
        batch_data = []
        for item in batch:
            batch_data.append(item.data)
        
        await save_can_signal_batch(batch_data)
        
        logger.debug(
            "can_signals_batch_flushed",
            count=len(batch_data)
        )
    
    async def _flush_telemetry_batch(self, batch: List[BatchItem]):
        """Flush telemetry batch."""
        if not batch:
            return
        
        from app.models import save_telemetry_batch
        
        batch_data = []
        for item in batch:
            batch_data.append(item.data)
        
        await save_telemetry_batch(batch_data)
        
        logger.debug(
            "telemetry_batch_flushed",
            count=len(batch_data)
        )
    
    def get_batch_stats(self) -> Dict[str, int]:
        """Get batch statistics."""
        return {
            batch_type: len(items) 
            for batch_type, items in self.batches.items()
        }


# Global batch processor
batch_processor = BatchProcessor()
