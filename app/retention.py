"""Data retention and cleanup policies."""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any
import structlog

logger = structlog.get_logger()


class RetentionManager:
    """Manages data retention and cleanup policies."""
    
    def __init__(self):
        self.policies = {
            "raw_frames": {
                "retention_days": 7,
                "archive_days": 3,
                "enabled": True
            },
            "can_raw": {
                "retention_days": 30,
                "archive_days": 7,
                "enabled": True
            },
            "can_signals": {
                "retention_days": 180,
                "archive_days": 90,
                "enabled": True
            },
            "telemetry_flat": {
                "retention_days": 365,
                "archive_days": 180,
                "enabled": True
            },
            "decode_errors": {
                "retention_days": 14,
                "archive_days": 7,
                "enabled": True
            }
        }
        self.running = False
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
    
    async def start(self):
        """Start retention manager."""
        self.running = True
        asyncio.create_task(self._cleanup_loop())
        logger.info("retention_manager_started")
    
    async def stop(self):
        """Stop retention manager."""
        self.running = False
        logger.info("retention_manager_stopped")
    
    async def _cleanup_loop(self):
        """Main cleanup loop."""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._run_cleanup()
            except Exception as e:
                logger.error("cleanup_loop_error", error=str(e))
    
    async def _run_cleanup(self):
        """Run cleanup for all tables."""
        current_time = time.time()
        
        for table_name, policy in self.policies.items():
            if not policy["enabled"]:
                continue
            
            try:
                await self._cleanup_table(table_name, policy)
            except Exception as e:
                logger.error("table_cleanup_error", table=table_name, error=str(e))
        
        self.last_cleanup = current_time
        logger.info("retention_cleanup_completed")
    
    async def _cleanup_table(self, table_name: str, policy: Dict[str, Any]):
        """Cleanup specific table."""
        retention_days = policy["retention_days"]
        archive_days = policy["archive_days"]
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        archive_date = datetime.utcnow() - timedelta(days=archive_days)
        
        if table_name == "raw_frames":
            await self._cleanup_raw_frames(cutoff_date, archive_date)
        elif table_name == "can_raw":
            await self._cleanup_can_raw(cutoff_date, archive_date)
        elif table_name == "can_signals":
            await self._cleanup_can_signals(cutoff_date, archive_date)
        elif table_name == "telemetry_flat":
            await self._cleanup_telemetry_flat(cutoff_date, archive_date)
        elif table_name == "decode_errors":
            await self._cleanup_decode_errors(cutoff_date, archive_date)
    
    async def _cleanup_raw_frames(self, cutoff_date: datetime, archive_date: datetime):
        """Cleanup raw_frames table."""
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Archive old data
            archive_query = text("""
                INSERT INTO raw_frames_archive 
                SELECT * FROM raw_frames 
                WHERE received_at < :archive_date
            """)
            await session.execute(archive_query, {"archive_date": archive_date})
            
            # Delete old data
            delete_query = text("""
                DELETE FROM raw_frames 
                WHERE received_at < :cutoff_date
            """)
            result = await session.execute(delete_query, {"cutoff_date": cutoff_date})
            await session.commit()
            
            logger.info(
                "raw_frames_cleanup",
                deleted_count=result.rowcount,
                cutoff_date=cutoff_date.isoformat()
            )
    
    async def _cleanup_can_raw(self, cutoff_date: datetime, archive_date: datetime):
        """Cleanup can_raw table."""
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Archive old data
            archive_query = text("""
                INSERT INTO can_raw_archive 
                SELECT * FROM can_raw 
                WHERE recv_time < :archive_date
            """)
            await session.execute(archive_query, {"archive_date": archive_date})
            
            # Delete old data
            delete_query = text("""
                DELETE FROM can_raw 
                WHERE recv_time < :cutoff_date
            """)
            result = await session.execute(delete_query, {"cutoff_date": cutoff_date})
            await session.commit()
            
            logger.info(
                "can_raw_cleanup",
                deleted_count=result.rowcount,
                cutoff_date=cutoff_date.isoformat()
            )
    
    async def _cleanup_can_signals(self, cutoff_date: datetime, archive_date: datetime):
        """Cleanup can_signals table."""
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Archive old data
            archive_query = text("""
                INSERT INTO can_signals_archive 
                SELECT * FROM can_signals 
                WHERE signal_time < :archive_date
            """)
            await session.execute(archive_query, {"archive_date": archive_date})
            
            # Delete old data
            delete_query = text("""
                DELETE FROM can_signals 
                WHERE signal_time < :cutoff_date
            """)
            result = await session.execute(delete_query, {"cutoff_date": cutoff_date})
            await session.commit()
            
            logger.info(
                "can_signals_cleanup",
                deleted_count=result.rowcount,
                cutoff_date=cutoff_date.isoformat()
            )
    
    async def _cleanup_telemetry_flat(self, cutoff_date: datetime, archive_date: datetime):
        """Cleanup telemetry_flat table."""
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Archive old data
            archive_query = text("""
                INSERT INTO telemetry_flat_archive 
                SELECT * FROM telemetry_flat 
                WHERE device_time < :archive_date
            """)
            await session.execute(archive_query, {"archive_date": archive_date})
            
            # Delete old data
            delete_query = text("""
                DELETE FROM telemetry_flat 
                WHERE device_time < :cutoff_date
            """)
            result = await session.execute(delete_query, {"cutoff_date": cutoff_date})
            await session.commit()
            
            logger.info(
                "telemetry_flat_cleanup",
                deleted_count=result.rowcount,
                cutoff_date=cutoff_date.isoformat()
            )
    
    async def _cleanup_decode_errors(self, cutoff_date: datetime, archive_date: datetime):
        """Cleanup decode_errors table."""
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            # Archive old data
            archive_query = text("""
                INSERT INTO decode_errors_archive 
                SELECT * FROM decode_errors 
                WHERE error_time < :archive_date
            """)
            await session.execute(archive_query, {"archive_date": archive_date})
            
            # Delete old data
            delete_query = text("""
                DELETE FROM decode_errors 
                WHERE error_time < :cutoff_date
            """)
            result = await session.execute(delete_query, {"cutoff_date": cutoff_date})
            await session.commit()
            
            logger.info(
                "decode_errors_cleanup",
                deleted_count=result.rowcount,
                cutoff_date=cutoff_date.isoformat()
            )
    
    def update_policy(self, table_name: str, policy: Dict[str, Any]):
        """Update retention policy for table."""
        if table_name in self.policies:
            self.policies[table_name].update(policy)
            logger.info("retention_policy_updated", table=table_name, policy=policy)
    
    def get_policies(self) -> Dict[str, Dict[str, Any]]:
        """Get all retention policies."""
        return dict(self.policies)


# Global retention manager
retention_manager = RetentionManager()
