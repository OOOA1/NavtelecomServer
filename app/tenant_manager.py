"""
Multi-tenant management system.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import structlog
from sqlalchemy import text
from app.db import AsyncSessionLocal

logger = structlog.get_logger()


class TenantManager:
    """Manages multi-tenant operations and isolation."""
    
    def __init__(self):
        self.tenant_cache: Dict[str, Dict[str, Any]] = {}
        self.tenant_quotas: Dict[str, Dict[str, Any]] = {}
        self.tenant_limits: Dict[str, Dict[str, Any]] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Default limits
        self.default_limits = {
            "max_frames_per_minute": 1000,
            "max_frames_per_hour": 10000,
            "max_frames_per_day": 100000,
            "max_can_frames_per_minute": 500,
            "max_can_frames_per_hour": 5000,
            "max_can_frames_per_day": 50000,
            "max_api_requests_per_minute": 100,
            "max_api_requests_per_hour": 1000,
            "max_api_requests_per_day": 10000,
            "max_storage_gb": 100,
            "max_devices": 1000
        }
        
        logger.info("tenant_manager_initialized")
    
    async def create_tenant(self, name: str, slug: str, description: str = "", 
                           settings: Dict[str, Any] = None, limits: Dict[str, Any] = None) -> str:
        """Create a new tenant."""
        tenant_id = str(uuid.uuid4())
        
        async with AsyncSessionLocal() as session:
            # Create tenant
            await session.execute(
                text("""
                    INSERT INTO tenants (id, name, slug, description, settings, limits)
                    VALUES (:id, :name, :slug, :description, :settings, :limits)
                """),
                {
                    "id": tenant_id,
                    "name": name,
                    "slug": slug,
                    "description": description,
                    "settings": settings or {},
                    "limits": limits or self.default_limits
                }
            )
            
            # Create default API key
            api_key = await self._generate_api_key()
            await session.execute(
                text("""
                    INSERT INTO tenant_api_keys (tenant_id, key_name, api_key, permissions)
                    VALUES (:tenant_id, :key_name, :api_key, :permissions)
                """),
                {
                    "tenant_id": tenant_id,
                    "key_name": "default",
                    "api_key": api_key,
                    "permissions": {"read": True, "write": True, "admin": False}
                }
            )
            
            # Create default quotas
            for quota_type, limit in (limits or self.default_limits).items():
                await session.execute(
                    text("""
                        INSERT INTO tenant_quotas (tenant_id, quota_type, quota_limit, quota_used)
                        VALUES (:tenant_id, :quota_type, :quota_limit, 0)
                    """),
                    {
                        "tenant_id": tenant_id,
                        "quota_type": quota_type,
                        "quota_limit": limit
                    }
                )
            
            await session.commit()
        
        # Update cache
        await self._load_tenant_cache(tenant_id)
        
        logger.info("tenant_created", tenant_id=tenant_id, name=name, slug=slug)
        return tenant_id
    
    async def get_tenant_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get tenant information by API key."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT t.id, t.name, t.slug, t.status, t.settings, t.limits,
                           tak.permissions, tak.rate_limit_per_minute, tak.rate_limit_per_hour, tak.rate_limit_per_day
                    FROM tenants t
                    JOIN tenant_api_keys tak ON t.id = tak.tenant_id
                    WHERE tak.api_key = :api_key AND tak.status = 'active' AND t.status = 'active'
                """),
                {"api_key": api_key}
            )
            
            row = result.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "slug": row[2],
                    "status": row[3],
                    "settings": row[4],
                    "limits": row[5],
                    "permissions": row[6],
                    "rate_limits": {
                        "per_minute": row[7],
                        "per_hour": row[8],
                        "per_day": row[9]
                    }
                }
        
        return None
    
    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant information by ID."""
        # Check cache first
        if tenant_id in self.tenant_cache:
            return self.tenant_cache[tenant_id]
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT id, name, slug, description, status, settings, limits, created_at, updated_at
                    FROM tenants
                    WHERE id = :tenant_id
                """),
                {"tenant_id": tenant_id}
            )
            
            row = result.fetchone()
            if row:
                tenant_data = {
                    "id": row[0],
                    "name": row[1],
                    "slug": row[2],
                    "description": row[3],
                    "status": row[4],
                    "settings": row[5],
                    "limits": row[6],
                    "created_at": row[7],
                    "updated_at": row[8]
                }
                
                # Cache the result
                self.tenant_cache[tenant_id] = tenant_data
                return tenant_data
        
        return None
    
    async def set_tenant_context(self, session, tenant_id: str):
        """Set tenant context for database session."""
        await session.execute(
            text("SELECT set_tenant_context(:tenant_id)"),
            {"tenant_id": tenant_id}
        )
    
    async def check_quota(self, tenant_id: str, quota_type: str, usage: int) -> bool:
        """Check if tenant has quota available."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT check_tenant_quota(:tenant_id, :quota_type, :usage)"),
                {
                    "tenant_id": tenant_id,
                    "quota_type": quota_type,
                    "usage": usage
                }
            )
            
            return result.scalar_one()
    
    async def update_quota(self, tenant_id: str, quota_type: str, usage: int):
        """Update tenant quota usage."""
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("SELECT update_tenant_quota(:tenant_id, :quota_type, :usage)"),
                {
                    "tenant_id": tenant_id,
                    "quota_type": quota_type,
                    "usage": usage
                }
            )
            await session.commit()
    
    async def update_usage(self, tenant_id: str, date: datetime, **usage_data):
        """Update tenant usage statistics."""
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    SELECT update_tenant_usage(
                        :tenant_id, :date, :frames_received, :frames_processed,
                        :can_frames_received, :can_signals_decoded, :api_requests, :storage_bytes
                    )
                """),
                {
                    "tenant_id": tenant_id,
                    "date": date.date(),
                    "frames_received": usage_data.get("frames_received", 0),
                    "frames_processed": usage_data.get("frames_processed", 0),
                    "can_frames_received": usage_data.get("can_frames_received", 0),
                    "can_signals_decoded": usage_data.get("can_signals_decoded", 0),
                    "api_requests": usage_data.get("api_requests", 0),
                    "storage_bytes": usage_data.get("storage_bytes", 0)
                }
            )
            await session.commit()
    
    async def get_tenant_usage(self, tenant_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get tenant usage statistics for a date range."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT date, frames_received, frames_processed, can_frames_received,
                           can_signals_decoded, api_requests, storage_bytes
                    FROM tenant_usage
                    WHERE tenant_id = :tenant_id AND date BETWEEN :start_date AND :end_date
                    ORDER BY date DESC
                """),
                {
                    "tenant_id": tenant_id,
                    "start_date": start_date.date(),
                    "end_date": end_date.date()
                }
            )
            
            return [
                {
                    "date": row[0],
                    "frames_received": row[1],
                    "frames_processed": row[2],
                    "can_frames_received": row[3],
                    "can_signals_decoded": row[4],
                    "api_requests": row[5],
                    "storage_bytes": row[6]
                }
                for row in result.fetchall()
            ]
    
    async def get_tenant_quotas(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant quota information."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT quota_type, quota_limit, quota_used, quota_reset_date
                    FROM tenant_quotas
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id}
            )
            
            quotas = {}
            for row in result.fetchall():
                quotas[row[0]] = {
                    "limit": row[1],
                    "used": row[2],
                    "reset_date": row[3],
                    "remaining": max(0, row[1] - row[2]) if row[1] else None
                }
            
            return quotas
    
    async def create_tenant_device(self, tenant_id: str, device_id: str, 
                                  device_name: str = "", device_type: str = "") -> str:
        """Create a tenant device."""
        device_uuid = str(uuid.uuid4())
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO tenant_devices (id, tenant_id, device_id, device_name, device_type)
                    VALUES (:id, :tenant_id, :device_id, :device_name, :device_type)
                """),
                {
                    "id": device_uuid,
                    "tenant_id": tenant_id,
                    "device_id": device_id,
                    "device_name": device_name,
                    "device_type": device_type
                }
            )
            await session.commit()
        
        logger.info("tenant_device_created", tenant_id=tenant_id, device_id=device_id, device_uuid=device_uuid)
        return device_uuid
    
    async def get_tenant_devices(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Get tenant devices."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT id, device_id, device_name, device_type, status, created_at, updated_at
                    FROM tenant_devices
                    WHERE tenant_id = :tenant_id
                    ORDER BY created_at DESC
                """),
                {"tenant_id": tenant_id}
            )
            
            return [
                {
                    "id": row[0],
                    "device_id": row[1],
                    "device_name": row[2],
                    "device_type": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                }
                for row in result.fetchall()
            ]
    
    async def create_api_key(self, tenant_id: str, key_name: str, 
                           permissions: Dict[str, bool] = None) -> str:
        """Create a new API key for tenant."""
        api_key = await self._generate_api_key()
        
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO tenant_api_keys (tenant_id, key_name, api_key, permissions)
                    VALUES (:tenant_id, :key_name, :api_key, :permissions)
                """),
                {
                    "tenant_id": tenant_id,
                    "key_name": key_name,
                    "api_key": api_key,
                    "permissions": permissions or {"read": True, "write": True, "admin": False}
                }
            )
            await session.commit()
        
        logger.info("api_key_created", tenant_id=tenant_id, key_name=key_name)
        return api_key
    
    async def revoke_api_key(self, tenant_id: str, api_key: str):
        """Revoke an API key."""
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE tenant_api_keys
                    SET status = 'revoked', updated_at = NOW()
                    WHERE tenant_id = :tenant_id AND api_key = :api_key
                """),
                {
                    "tenant_id": tenant_id,
                    "api_key": api_key
                }
            )
            await session.commit()
        
        logger.info("api_key_revoked", tenant_id=tenant_id, api_key=api_key)
    
    async def get_tenant_billing(self, tenant_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get tenant billing information."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT billing_period_start, billing_period_end, frames_received, frames_processed,
                           can_frames_received, can_signals_decoded, api_requests, storage_bytes,
                           total_cost, status
                    FROM tenant_billing
                    WHERE tenant_id = :tenant_id 
                    AND billing_period_start BETWEEN :start_date AND :end_date
                    ORDER BY billing_period_start DESC
                """),
                {
                    "tenant_id": tenant_id,
                    "start_date": start_date.date(),
                    "end_date": end_date.date()
                }
            )
            
            return [
                {
                    "period_start": row[0],
                    "period_end": row[1],
                    "frames_received": row[2],
                    "frames_processed": row[3],
                    "can_frames_received": row[4],
                    "can_signals_decoded": row[5],
                    "api_requests": row[6],
                    "storage_bytes": row[7],
                    "total_cost": row[8],
                    "status": row[9]
                }
                for row in result.fetchall()
            ]
    
    async def _generate_api_key(self) -> str:
        """Generate a secure API key."""
        import secrets
        return f"navtel_{secrets.token_urlsafe(32)}"
    
    async def _load_tenant_cache(self, tenant_id: str):
        """Load tenant data into cache."""
        tenant_data = await self.get_tenant_by_id(tenant_id)
        if tenant_data:
            self.tenant_cache[tenant_id] = tenant_data
    
    async def _monitor_tenant_quotas(self):
        """Background task to monitor tenant quotas."""
        while True:
            try:
                # Check quota usage and send alerts
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        text("""
                            SELECT t.id, t.name, tq.quota_type, tq.quota_limit, tq.quota_used
                            FROM tenants t
                            JOIN tenant_quotas tq ON t.id = tq.tenant_id
                            WHERE t.status = 'active'
                            AND tq.quota_used > (tq.quota_limit * 0.8)
                        """)
                    )
                    
                    for row in result.fetchall():
                        tenant_id, tenant_name, quota_type, quota_limit, quota_used = row
                        
                        if quota_used >= quota_limit:
                            # Quota exceeded
                            from app.alerts import alert_manager, AlertSeverity
                            alert_manager.raise_alert(
                                name=f"TenantQuotaExceeded_{quota_type}",
                                severity=AlertSeverity.CRITICAL,
                                message=f"Tenant {tenant_name} has exceeded quota for {quota_type}",
                                labels={
                                    "tenant_id": tenant_id,
                                    "tenant_name": tenant_name,
                                    "quota_type": quota_type
                                },
                                value=quota_used,
                                threshold=quota_limit
                            )
                        elif quota_used > (quota_limit * 0.8):
                            # Quota warning
                            from app.alerts import alert_manager, AlertSeverity
                            alert_manager.raise_alert(
                                name=f"TenantQuotaWarning_{quota_type}",
                                severity=AlertSeverity.WARNING,
                                message=f"Tenant {tenant_name} is approaching quota limit for {quota_type}",
                                labels={
                                    "tenant_id": tenant_id,
                                    "tenant_name": tenant_name,
                                    "quota_type": quota_type
                                },
                                value=quota_used,
                                threshold=quota_limit
                            )
                
                # Clean cache every hour
                if len(self.tenant_cache) > 1000:
                    self.tenant_cache.clear()
                
            except Exception as e:
                logger.error("tenant_quota_monitoring_error", error=str(e))
            
            # Check every 5 minutes
            await asyncio.sleep(300)
    
    async def start_monitoring(self):
        """Start tenant monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_tenant_quotas())
            logger.info("tenant_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop tenant monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("tenant_monitoring_stopped")
            self.monitoring_task = None


tenant_manager = TenantManager()

