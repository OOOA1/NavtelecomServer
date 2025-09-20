"""Security and authentication for API."""
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

logger = structlog.get_logger()

# Security configuration
API_KEYS = {
    "admin": "admin-secret-key-12345",
    "readonly": "readonly-secret-key-67890",
    "integration": "integration-secret-key-abcde"
}

HMAC_SECRET = "your-hmac-secret-key-here"

security = HTTPBearer()


class SecurityManager:
    """Manages API security and authentication."""
    
    def __init__(self):
        self.rate_limits: Dict[str, Dict[str, Any]] = {}
        self.blocked_ips: set = set()
    
    def verify_api_key(self, api_key: str) -> Optional[str]:
        """Verify API key and return role."""
        for role, key in API_KEYS.items():
            if hmac.compare_digest(api_key, key):
                return role
        return None
    
    def verify_hmac_signature(self, payload: bytes, signature: str, timestamp: str) -> bool:
        """Verify HMAC signature."""
        try:
            # Check timestamp (within 5 minutes)
            current_time = int(time.time())
            request_time = int(timestamp)
            if abs(current_time - request_time) > 300:  # 5 minutes
                return False
            
            # Create expected signature
            message = f"{timestamp}:{payload.decode()}"
            expected_signature = hmac.new(
                HMAC_SECRET.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error("hmac_verification_error", error=str(e))
            return False
    
    def check_rate_limit(self, client_ip: str, endpoint: str) -> bool:
        """Check rate limit for client."""
        current_time = time.time()
        key = f"{client_ip}:{endpoint}"
        
        if key not in self.rate_limits:
            self.rate_limits[key] = {
                "count": 0,
                "window_start": current_time
            }
        
        rate_info = self.rate_limits[key]
        
        # Reset window if needed (1 minute window)
        if current_time - rate_info["window_start"] > 60:
            rate_info["count"] = 0
            rate_info["window_start"] = current_time
        
        # Check limit (100 requests per minute)
        if rate_info["count"] >= 100:
            return False
        
        rate_info["count"] += 1
        return True
    
    def block_ip(self, ip: str):
        """Block IP address."""
        self.blocked_ips.add(ip)
        logger.warning("ip_blocked", ip=ip)
    
    def unblock_ip(self, ip: str):
        """Unblock IP address."""
        self.blocked_ips.discard(ip)
        logger.info("ip_unblocked", ip=ip)
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is blocked."""
        return ip in self.blocked_ips


# Global security manager
security_manager = SecurityManager()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Get current user from API key."""
    api_key = credentials.credentials
    role = security_manager.verify_api_key(api_key)
    
    if not role:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return role


async def require_role(required_role: str):
    """Require specific role."""
    def role_checker(current_user: str = Depends(get_current_user)):
        if current_user != required_role and current_user != "admin":
            raise HTTPException(
                status_code=403,
                detail=f"Requires {required_role} role"
            )
        return current_user
    return role_checker


async def check_security(request: Request):
    """Check security for request."""
    client_ip = request.client.host
    
    # Check if IP is blocked
    if security_manager.is_ip_blocked(client_ip):
        raise HTTPException(
            status_code=403,
            detail="IP address blocked"
        )
    
    # Check rate limit
    endpoint = request.url.path
    if not security_manager.check_rate_limit(client_ip, endpoint):
        # Block IP after too many requests
        security_manager.block_ip(client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )
    
    return client_ip


def verify_hmac_auth(request: Request):
    """Verify HMAC authentication."""
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")
    
    if not signature or not timestamp:
        raise HTTPException(
            status_code=401,
            detail="Missing HMAC signature or timestamp"
        )
    
    # Get request body
    body = request.body()
    
    if not security_manager.verify_hmac_signature(body, signature, timestamp):
        raise HTTPException(
            status_code=401,
            detail="Invalid HMAC signature"
        )
    
    return True
