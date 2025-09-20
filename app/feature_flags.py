"""
Feature flags system for zero-downtime deployments.
"""
import os
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import structlog
from sqlalchemy import text
from app.db import AsyncSessionLocal

logger = structlog.get_logger()


class FeatureFlags:
    """Feature flags manager for safe deployments."""
    
    def __init__(self):
        self.flags: Dict[str, bool] = {}
        self.flag_metadata: Dict[str, Dict[str, Any]] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Load flags from environment
        self._load_env_flags()
        
        logger.info("feature_flags_initialized", flags=list(self.flags.keys()))
    
    def _load_env_flags(self):
        """Load feature flags from environment variables."""
        env_flags = {
            "FF_SHADOW_WRITE": os.getenv("FF_SHADOW_WRITE", "false").lower() == "true",
            "FF_READ_NEW": os.getenv("FF_READ_NEW", "false").lower() == "true",
            "FF_CANARY_DEPLOY": os.getenv("FF_CANARY_DEPLOY", "false").lower() == "true",
            "FF_NEW_API_V2": os.getenv("FF_NEW_API_V2", "false").lower() == "true",
            "FF_BATCH_PROCESSING": os.getenv("FF_BATCH_PROCESSING", "true").lower() == "true",
            "FF_TENANT_ISOLATION": os.getenv("FF_TENANT_ISOLATION", "true").lower() == "true",
            "FF_SECURITY_MONITORING": os.getenv("FF_SECURITY_MONITORING", "true").lower() == "true",
            "FF_BACKUP_MONITORING": os.getenv("FF_BACKUP_MONITORING", "true").lower() == "true",
        }
        
        for flag, value in env_flags.items():
            self.flags[flag] = value
            self.flag_metadata[flag] = {
                "source": "environment",
                "updated_at": datetime.now(timezone.utc),
                "description": self._get_flag_description(flag)
            }
    
    def _get_flag_description(self, flag: str) -> str:
        """Get description for a feature flag."""
        descriptions = {
            "FF_SHADOW_WRITE": "Enable shadow writes to new fields/tables",
            "FF_READ_NEW": "Read from new fields/tables instead of old ones",
            "FF_CANARY_DEPLOY": "Enable canary deployment for new features",
            "FF_NEW_API_V2": "Enable new API v2 endpoints",
            "FF_BATCH_PROCESSING": "Enable batch processing for better performance",
            "FF_TENANT_ISOLATION": "Enable tenant isolation and load balancing",
            "FF_SECURITY_MONITORING": "Enable security monitoring and threat detection",
            "FF_BACKUP_MONITORING": "Enable backup monitoring and alerts"
        }
        return descriptions.get(flag, "Unknown feature flag")
    
    def is_enabled(self, flag: str) -> bool:
        """Check if a feature flag is enabled."""
        return self.flags.get(flag, False)
    
    def is_disabled(self, flag: str) -> bool:
        """Check if a feature flag is disabled."""
        return not self.is_enabled(flag)
    
    def get_flag(self, flag: str) -> bool:
        """Get feature flag value."""
        return self.is_enabled(flag)
    
    def set_flag(self, flag: str, value: bool, description: str = ""):
        """Set a feature flag value."""
        self.flags[flag] = value
        self.flag_metadata[flag] = {
            "source": "runtime",
            "updated_at": datetime.now(timezone.utc),
            "description": description or self._get_flag_description(flag)
        }
        
        logger.info("feature_flag_updated", flag=flag, value=value, description=description)
    
    def get_all_flags(self) -> Dict[str, Dict[str, Any]]:
        """Get all feature flags with metadata."""
        result = {}
        for flag, value in self.flags.items():
            result[flag] = {
                "value": value,
                "metadata": self.flag_metadata.get(flag, {})
            }
        return result
    
    async def load_flags_from_db(self):
        """Load feature flags from database."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("""
                        SELECT flag_name, flag_value, description, updated_at
                        FROM feature_flags
                        WHERE status = 'active'
                    """)
                )
                
                for row in result.fetchall():
                    flag_name, flag_value, description, updated_at = row
                    self.flags[flag_name] = flag_value
                    self.flag_metadata[flag_name] = {
                        "source": "database",
                        "updated_at": updated_at,
                        "description": description
                    }
                
                logger.info("feature_flags_loaded_from_db", count=len(self.flags))
                
        except Exception as e:
            logger.error("failed_to_load_flags_from_db", error=str(e))
    
    async def save_flags_to_db(self):
        """Save feature flags to database."""
        try:
            async with AsyncSessionLocal() as session:
                for flag, value in self.flags.items():
                    metadata = self.flag_metadata.get(flag, {})
                    
                    await session.execute(
                        text("""
                            INSERT INTO feature_flags (flag_name, flag_value, description, status, updated_at)
                            VALUES (:flag_name, :flag_value, :description, 'active', :updated_at)
                            ON CONFLICT (flag_name)
                            DO UPDATE SET
                                flag_value = EXCLUDED.flag_value,
                                description = EXCLUDED.description,
                                updated_at = EXCLUDED.updated_at
                        """),
                        {
                            "flag_name": flag,
                            "flag_value": value,
                            "description": metadata.get("description", ""),
                            "updated_at": metadata.get("updated_at", datetime.now(timezone.utc))
                        }
                    )
                
                await session.commit()
                logger.info("feature_flags_saved_to_db", count=len(self.flags))
                
        except Exception as e:
            logger.error("failed_to_save_flags_to_db", error=str(e))
    
    def should_shadow_write(self, feature: str) -> bool:
        """Check if shadow writes should be enabled for a feature."""
        if not self.is_enabled("FF_SHADOW_WRITE"):
            return False
        
        # Feature-specific shadow write flags
        feature_flags = {
            "raw_frames": self.is_enabled("FF_SHADOW_WRITE_RAW_FRAMES"),
            "can_frames": self.is_enabled("FF_SHADOW_WRITE_CAN_FRAMES"),
            "telemetry": self.is_enabled("FF_SHADOW_WRITE_TELEMETRY"),
            "tenant_data": self.is_enabled("FF_SHADOW_WRITE_TENANT_DATA")
        }
        
        return feature_flags.get(feature, self.is_enabled("FF_SHADOW_WRITE"))
    
    def should_read_new(self, feature: str) -> bool:
        """Check if new fields/tables should be read for a feature."""
        if not self.is_enabled("FF_READ_NEW"):
            return False
        
        # Feature-specific read flags
        feature_flags = {
            "raw_frames": self.is_enabled("FF_READ_NEW_RAW_FRAMES"),
            "can_frames": self.is_enabled("FF_READ_NEW_CAN_FRAMES"),
            "telemetry": self.is_enabled("FF_READ_NEW_TELEMETRY"),
            "tenant_data": self.is_enabled("FF_READ_NEW_TENANT_DATA")
        }
        
        return feature_flags.get(feature, self.is_enabled("FF_READ_NEW"))
    
    def is_canary_enabled(self, feature: str) -> bool:
        """Check if canary deployment is enabled for a feature."""
        if not self.is_enabled("FF_CANARY_DEPLOY"):
            return False
        
        # Feature-specific canary flags
        feature_flags = {
            "api_v2": self.is_enabled("FF_CANARY_API_V2"),
            "new_processing": self.is_enabled("FF_CANARY_NEW_PROCESSING"),
            "tenant_features": self.is_enabled("FF_CANARY_TENANT_FEATURES")
        }
        
        return feature_flags.get(feature, self.is_enabled("FF_CANARY_DEPLOY"))
    
    def get_canary_percentage(self, feature: str) -> int:
        """Get canary percentage for a feature."""
        if not self.is_canary_enabled(feature):
            return 0
        
        # Feature-specific canary percentages
        percentages = {
            "api_v2": int(os.getenv("FF_CANARY_API_V2_PERCENTAGE", "5")),
            "new_processing": int(os.getenv("FF_CANARY_NEW_PROCESSING_PERCENTAGE", "10")),
            "tenant_features": int(os.getenv("FF_CANARY_TENANT_FEATURES_PERCENTAGE", "5"))
        }
        
        return percentages.get(feature, 5)
    
    def should_use_canary(self, feature: str, identifier: str) -> bool:
        """Check if a specific identifier should use canary feature."""
        if not self.is_canary_enabled(feature):
            return False
        
        percentage = self.get_canary_percentage(feature)
        
        # Simple hash-based canary selection
        import hashlib
        hash_value = int(hashlib.md5(identifier.encode()).hexdigest(), 16)
        return (hash_value % 100) < percentage
    
    async def _monitor_flags(self):
        """Background task to monitor feature flags."""
        while True:
            try:
                # Reload flags from database
                await self.load_flags_from_db()
                
                # Log flag status
                enabled_flags = [flag for flag, value in self.flags.items() if value]
                if enabled_flags:
                    logger.info("active_feature_flags", flags=enabled_flags)
                
            except Exception as e:
                logger.error("feature_flag_monitoring_error", error=str(e))
            
            # Check every 5 minutes
            await asyncio.sleep(300)
    
    async def start_monitoring(self):
        """Start feature flag monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_flags())
            logger.info("feature_flag_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop feature flag monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("feature_flag_monitoring_stopped")
            self.monitoring_task = None


# Global feature flags instance
feature_flags = FeatureFlags()

