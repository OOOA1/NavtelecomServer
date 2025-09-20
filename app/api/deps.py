"""
Common dependencies for API endpoints.
"""
import uuid
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

from app.tenant_manager import tenant_manager
from app.feature_flags import feature_flags
from app.security_monitor import security_monitor

logger = structlog.get_logger()

# Security scheme
security = HTTPBearer()


async def get_tenant_from_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Get tenant information from API key."""
    api_key = credentials.credentials
    
    # Check if API key is blocked
    if security_monitor.is_ip_blocked("api_key_check"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key blocked"
        )
    
    # Get tenant from API key
    tenant = await tenant_manager.get_tenant_by_api_key(api_key)
    if not tenant:
        # Record failed auth attempt
        security_monitor.record_failed_auth("api_key", api_key, "api_auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Record successful auth
    security_monitor.record_connection_attempt("api_key", True)
    
    return tenant


async def get_tenant_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Get tenant from request headers or API key."""
    # Try to get tenant from API key first
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
            return await tenant_manager.get_tenant_by_api_key(api_key)
    except Exception:
        pass
    
    # Try to get tenant from headers
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return await tenant_manager.get_tenant_by_id(tenant_id)
    
    return None


async def get_idempotency_key(request: Request) -> Optional[str]:
    """Get idempotency key from request headers."""
    idempotency_key = request.headers.get("Idempotency-Key")
    
    if idempotency_key:
        # Validate UUID format
        try:
            uuid.UUID(idempotency_key)
            return idempotency_key
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid idempotency key format"
            )
    
    return None


async def get_trace_id(request: Request) -> str:
    """Get or generate trace ID for request."""
    trace_id = request.headers.get("X-Trace-ID")
    if not trace_id:
        trace_id = str(uuid.uuid4())
    
    return trace_id


async def get_canary_flag(request: Request) -> bool:
    """Check if request should use canary version."""
    # Check explicit canary header
    if request.headers.get("X-Canary") == "1":
        return True
    
    # Check canary percentage based on trace ID
    trace_id = await get_trace_id(request)
    return feature_flags.should_use_canary("api_v2", trace_id)


async def get_api_version(request: Request) -> str:
    """Get API version from request path."""
    path = request.url.path
    
    if path.startswith("/api/v2/"):
        return "v2"
    elif path.startswith("/api/v1/"):
        return "v1"
    else:
        return "v1"  # Default to v1


async def check_rate_limit(tenant: Dict[str, Any], request: Request) -> None:
    """Check rate limits for tenant."""
    # Get rate limits from tenant
    rate_limits = tenant.get("rate_limits", {})
    
    # Check per-minute limit
    per_minute = rate_limits.get("per_minute", 1000)
    # Check per-hour limit
    per_hour = rate_limits.get("per_hour", 10000)
    # Check per-day limit
    per_day = rate_limits.get("per_day", 100000)
    
    # TODO: Implement actual rate limiting logic
    # This would typically use Redis or similar for tracking
    
    # For now, just log the check
    logger.debug("rate_limit_check", 
                tenant_id=tenant["id"], 
                per_minute=per_minute,
                per_hour=per_hour,
                per_day=per_day)


async def get_tenant_context(tenant: Dict[str, Any]) -> Dict[str, Any]:
    """Get tenant context for database operations."""
    return {
        "tenant_id": tenant["id"],
        "tenant_name": tenant["name"],
        "permissions": tenant.get("permissions", {}),
        "rate_limits": tenant.get("rate_limits", {})
    }


# Common response models
class ErrorResponse:
    """Standard error response format."""
    
    def __init__(self, code: str, message: str, trace_id: str, details: Optional[Dict[str, Any]] = None):
        self.error = {
            "code": code,
            "message": message,
            "trace_id": trace_id
        }
        if details:
            self.error["details"] = details


class SuccessResponse:
    """Standard success response format."""
    
    def __init__(self, data: Any, trace_id: str, meta: Optional[Dict[str, Any]] = None):
        self.data = data
        self.trace_id = trace_id
        if meta:
            self.meta = meta


# Pagination models
class PaginationParams:
    """Pagination parameters."""
    
    def __init__(self, cursor: Optional[str] = None, limit: int = 100):
        self.cursor = cursor
        self.limit = min(limit, 1000)  # Max limit


class PaginatedResponse:
    """Paginated response format."""
    
    def __init__(self, items: list, next_cursor: Optional[str] = None, 
                 total_estimate: Optional[int] = None, trace_id: str = None):
        self.items = items
        self.next_cursor = next_cursor
        self.trace_id = trace_id
        if total_estimate is not None:
            self.meta = {"total_estimate": total_estimate}

