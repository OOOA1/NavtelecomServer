"""
Reprocessing system for re-decoding historical data with updated dictionaries.
"""
import asyncio
import hashlib
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import structlog

from app.db import AsyncSessionLocal
from app.can_parser import can_parser
from app.models import save_can_signal_batch, get_can_raw_frames
from sqlalchemy import text

logger = structlog.get_logger()

@dataclass
class ReprocessingJob:
    """Reprocessing job definition."""
    id: str
    name: str
    description: str
    dict_version: str
    device_ids: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    batch_size: int = 1000
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    total_records: int = 0
    processed_records: int = 0
    error_count: int = 0
    error_message: Optional[str] = None

class ReprocessingManager:
    """Manages reprocessing jobs for dictionary updates."""
    
    def __init__(self):
        self.active_jobs: Dict[str, ReprocessingJob] = {}
        self.job_history: List[ReprocessingJob] = []
        self._running = False
        self._monitoring_task = None
    
    async def start(self):
        """Start reprocessing manager."""
        if not self._running:
            self._running = True
            self._monitoring_task = asyncio.create_task(self._monitor_jobs())
            logger.info("reprocessing_manager_started")
    
    async def stop(self):
        """Stop reprocessing manager."""
        if self._running:
            self._running = False
            if self._monitoring_task:
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            logger.info("reprocessing_manager_stopped")
    
    def get_dict_version(self) -> str:
        """Get current dictionary version hash."""
        # Calculate hash of all dictionary files
        dict_files = [
            "dicts/j1939.yaml",
            "dicts/obd2.yaml", 
            "dicts/volvo.yaml",
            "dicts/scania.yaml"
        ]
        
        combined_hash = hashlib.md5()
        for dict_file in dict_files:
            try:
                with open(dict_file, 'rb') as f:
                    combined_hash.update(f.read())
            except FileNotFoundError:
                # File doesn't exist, skip
                pass
        
        return combined_hash.hexdigest()[:16]
    
    async def create_reprocessing_job(
        self,
        name: str,
        description: str,
        device_ids: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        batch_size: int = 1000
    ) -> str:
        """Create a new reprocessing job."""
        job_id = f"reprocess_{int(datetime.now().timestamp())}"
        dict_version = self.get_dict_version()
        
        job = ReprocessingJob(
            id=job_id,
            name=name,
            description=description,
            dict_version=dict_version,
            device_ids=device_ids,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            created_at=datetime.now(timezone.utc)
        )
        
        # Estimate total records
        job.total_records = await self._estimate_records(job)
        
        self.active_jobs[job_id] = job
        logger.info(
            "reprocessing_job_created",
            job_id=job_id,
            name=name,
            total_records=job.total_records
        )
        
        return job_id
    
    async def start_job(self, job_id: str) -> bool:
        """Start a reprocessing job."""
        if job_id not in self.active_jobs:
            logger.error("reprocessing_job_not_found", job_id=job_id)
            return False
        
        job = self.active_jobs[job_id]
        if job.status != "pending":
            logger.error("reprocessing_job_not_pending", job_id=job_id, status=job.status)
            return False
        
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        
        # Start reprocessing in background
        asyncio.create_task(self._run_reprocessing_job(job))
        
        logger.info("reprocessing_job_started", job_id=job_id)
        return True
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a reprocessing job."""
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        if job.status == "running":
            job.status = "cancelled"
            logger.info("reprocessing_job_cancelled", job_id=job_id)
            return True
        
        return False
    
    async def get_job_status(self, job_id: str) -> Optional[ReprocessingJob]:
        """Get job status."""
        return self.active_jobs.get(job_id)
    
    async def list_jobs(self) -> List[ReprocessingJob]:
        """List all jobs (active and completed)."""
        all_jobs = list(self.active_jobs.values()) + self.job_history
        return sorted(all_jobs, key=lambda j: j.created_at, reverse=True)
    
    async def _estimate_records(self, job: ReprocessingJob) -> int:
        """Estimate number of records to reprocess."""
        async with AsyncSessionLocal() as session:
            query = "SELECT COUNT(*) FROM can_raw WHERE 1=1"
            params = {}
            
            if job.device_ids:
                device_placeholders = ",".join([f":device_{i}" for i in range(len(job.device_ids))])
                query += f" AND device_id IN ({device_placeholders})"
                for i, device_id in enumerate(job.device_ids):
                    params[f"device_{i}"] = device_id
            
            if job.start_time:
                query += " AND recv_time >= :start_time"
                params["start_time"] = job.start_time
            
            if job.end_time:
                query += " AND recv_time <= :end_time"
                params["end_time"] = job.end_time
            
            result = await session.execute(text(query), params)
            return result.scalar() or 0
    
    async def _run_reprocessing_job(self, job: ReprocessingJob):
        """Run a reprocessing job."""
        try:
            logger.info("reprocessing_job_started", job_id=job.id, total_records=job.total_records)
            
            offset = 0
            while offset < job.total_records:
                if job.status != "running":
                    break
                
                # Fetch batch of raw CAN frames
                batch = await self._fetch_batch(job, offset, job.batch_size)
                if not batch:
                    break
                
                # Reprocess batch
                processed_count, error_count = await self._reprocess_batch(job, batch)
                
                # Update progress
                job.processed_records += processed_count
                job.error_count += error_count
                job.progress = (job.processed_records / job.total_records) * 100
                
                offset += job.batch_size
                
                logger.debug(
                    "reprocessing_batch_completed",
                    job_id=job.id,
                    processed=processed_count,
                    errors=error_count,
                    progress=job.progress
                )
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            # Mark job as completed
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            
            logger.info(
                "reprocessing_job_completed",
                job_id=job.id,
                total_processed=job.processed_records,
                total_errors=job.error_count
            )
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            
            logger.error(
                "reprocessing_job_failed",
                job_id=job.id,
                error=str(e)
            )
        
        finally:
            # Move to history
            self.job_history.append(job)
            if job.id in self.active_jobs:
                del self.active_jobs[job.id]
    
    async def _fetch_batch(self, job: ReprocessingJob, offset: int, limit: int) -> List[Dict]:
        """Fetch a batch of raw CAN frames for reprocessing."""
        async with AsyncSessionLocal() as session:
            query = """
                SELECT id, device_id, can_id, payload, recv_time, dict_version
                FROM can_raw 
                WHERE 1=1
            """
            params = {"offset": offset, "limit": limit}
            
            if job.device_ids:
                device_placeholders = ",".join([f":device_{i}" for i in range(len(job.device_ids))])
                query += f" AND device_id IN ({device_placeholders})"
                for i, device_id in enumerate(job.device_ids):
                    params[f"device_{i}"] = device_id
            
            if job.start_time:
                query += " AND recv_time >= :start_time"
                params["start_time"] = job.start_time
            
            if job.end_time:
                query += " AND recv_time <= :end_time"
                params["end_time"] = job.end_time
            
            # Only reprocess frames with different dict version
            query += " AND (dict_version IS NULL OR dict_version != :current_version)"
            params["current_version"] = job.dict_version
            
            query += " ORDER BY recv_time LIMIT :limit OFFSET :offset"
            
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "can_id": row[2],
                    "payload": row[3],
                    "recv_time": row[4],
                    "dict_version": row[5]
                }
                for row in rows
            ]
    
    async def _reprocess_batch(self, job: ReprocessingJob, batch: List[Dict]) -> Tuple[int, int]:
        """Reprocess a batch of CAN frames."""
        processed_count = 0
        error_count = 0
        
        # Parse CAN frames with current dictionary
        signals_to_save = []
        
        for frame in batch:
            try:
                # Parse with current dictionary
                signals = can_parser.parse_can_frame(
                    frame["can_id"], 
                    frame["payload"], 
                    frame["device_id"]
                )
                
                # Prepare signals for batch save
                for signal in signals:
                    signals_to_save.append({
                        "raw_frame_id": frame["id"],
                        "device_id": frame["device_id"],
                        "can_id": frame["can_id"],
                        "signal_name": signal.name,
                        "signal_value": signal.value,
                        "signal_unit": signal.unit,
                        "pgn": signal.pgn,
                        "spn": signal.spn,
                        "mode": signal.mode,
                        "pid": signal.pid,
                        "recv_time": frame["recv_time"],
                        "dict_version": job.dict_version
                    })
                
                processed_count += 1
                
            except Exception as e:
                logger.warning(
                    "reprocessing_frame_error",
                    frame_id=frame["id"],
                    error=str(e)
                )
                error_count += 1
        
        # Batch save signals
        if signals_to_save:
            await save_can_signal_batch(signals_to_save)
        
        # Update dict_version for processed frames
        if processed_count > 0:
            await self._update_frame_dict_version(
                [frame["id"] for frame in batch[:processed_count]], 
                job.dict_version
            )
        
        return processed_count, error_count
    
    async def _update_frame_dict_version(self, frame_ids: List[int], dict_version: str):
        """Update dict_version for processed frames."""
        async with AsyncSessionLocal() as session:
            query = """
                UPDATE can_raw 
                SET dict_version = :dict_version 
                WHERE id = ANY(:frame_ids)
            """
            await session.execute(text(query), {
                "dict_version": dict_version,
                "frame_ids": frame_ids
            })
            await session.commit()
    
    async def _monitor_jobs(self):
        """Monitor running jobs."""
        while self._running:
            try:
                # Check for stuck jobs (running for more than 24 hours)
                current_time = datetime.now(timezone.utc)
                for job in list(self.active_jobs.values()):
                    if (job.status == "running" and 
                        job.started_at and 
                        current_time - job.started_at > timedelta(hours=24)):
                        
                        logger.warning(
                            "reprocessing_job_stuck",
                            job_id=job.id,
                            running_time=current_time - job.started_at
                        )
                        job.status = "failed"
                        job.error_message = "Job stuck - running for more than 24 hours"
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("reprocessing_monitor_error", error=str(e))
                await asyncio.sleep(60)

# Global reprocessing manager instance
reprocessing_manager = ReprocessingManager()
