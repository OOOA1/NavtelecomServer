"""
Idempotency middleware for API endpoints.
"""
import json
import hashlib
from typing import Dict, Any, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import structlog
from sqlalchemy import text
from app.db import AsyncSessionLocal

logger = structlog.get_logger()


class IdempotencyManager:
    """Manages idempotency for API requests."""
    
    def __init__(self):
        self.cache_ttl = 3600  # 1 hour
        self.max_cache_size = 10000
        
    async def check_idempotency(self, request: Request, tenant_id: str, 
                               idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Check if request is idempotent."""
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(request, tenant_id, idempotency_key)
            
            # Check cache
            cached_response = await self._get_cached_response(cache_key)
            if cached_response:
                logger.info("idempotent_request_found", 
                           idempotency_key=idempotency_key,
                           cache_key=cache_key)
                return cached_response
            
            return None
            
        except Exception as e:
            logger.error("idempotency_check_error", 
                        idempotency_key=idempotency_key, 
                        error=str(e))
            return None
    
    async def store_response(self, request: Request, tenant_id: str, 
                           idempotency_key: str, response_data: Dict[str, Any]) -> None:
        """Store response for idempotency."""
        try:
            # Generate cache key
            cache_key = self._generate_cache_key(request, tenant_id, idempotency_key)
            
            # Store in cache
            await self._store_cached_response(cache_key, response_data)
            
            logger.debug("idempotent_response_stored", 
                        idempotency_key=idempotency_key,
                        cache_key=cache_key)
            
        except Exception as e:
            logger.error("idempotency_store_error", 
                        idempotency_key=idempotency_key, 
                        error=str(e))
    
    def _generate_cache_key(self, request: Request, tenant_id: str, 
                           idempotency_key: str) -> str:
        """Generate cache key for idempotency."""
        # Include method, path, and body in hash
        method = request.method
        path = request.url.path
        query_params = str(request.query_params)
        
        # Get request body if available
        body = ""
        if hasattr(request, '_body'):
            body = request._body.decode('utf-8') if request._body else ""
        
        # Create hash
        content = f"{method}:{path}:{query_params}:{body}:{tenant_id}:{idempotency_key}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response from database."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("""
                        SELECT response_data, created_at
                        FROM idempotency_cache
                        WHERE cache_key = :cache_key
                        AND created_at > NOW() - INTERVAL '1 hour'
                    """),
                    {"cache_key": cache_key}
                )
                
                row = result.fetchone()
                if row:
                    return row[0]  # response_data
                
                return None
                
        except Exception as e:
            logger.error("idempotency_cache_get_error", 
                        cache_key=cache_key, 
                        error=str(e))
            return None
    
    async def _store_cached_response(self, cache_key: str, response_data: Dict[str, Any]) -> None:
        """Store response in cache."""
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text("""
                        INSERT INTO idempotency_cache (cache_key, response_data, created_at)
                        VALUES (:cache_key, :response_data, NOW())
                        ON CONFLICT (cache_key)
                        DO UPDATE SET
                            response_data = EXCLUDED.response_data,
                            created_at = EXCLUDED.created_at
                    """),
                    {
                        "cache_key": cache_key,
                        "response_data": json.dumps(response_data)
                    }
                )
                await session.commit()
                
        except Exception as e:
            logger.error("idempotency_cache_store_error", 
                        cache_key=cache_key, 
                        error=str(e))
    
    async def cleanup_expired_cache(self) -> None:
        """Clean up expired cache entries."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("""
                        DELETE FROM idempotency_cache
                        WHERE created_at < NOW() - INTERVAL '1 hour'
                    """)
                )
                await session.commit()
                
                deleted_count = result.rowcount
                if deleted_count > 0:
                    logger.info("idempotency_cache_cleaned", deleted_count=deleted_count)
                    
        except Exception as e:
            logger.error("idempotency_cache_cleanup_error", error=str(e))


# Global idempotency manager
idempotency_manager = IdempotencyManager()


async def idempotency_middleware(request: Request, call_next):
    """Idempotency middleware for FastAPI."""
    
    # Only apply to mutating methods
    if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
        response = await call_next(request)
        return response
    
    # Get idempotency key
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        response = await call_next(request)
        return response
    
    # Get tenant ID
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        response = await call_next(request)
        return response
    
    # Check for cached response
    cached_response = await idempotency_manager.check_idempotency(
        request, tenant_id, idempotency_key
    )
    
    if cached_response:
        # Return cached response
        return JSONResponse(
            content=cached_response,
            status_code=200,
            headers={
                "X-Idempotent": "true",
                "X-Cache-Key": idempotency_key
            }
        )
    
    # Process request
    response = await call_next(request)
    
    # Store response if successful
    if response.status_code < 400:
        try:
            response_body = response.body.decode('utf-8') if response.body else "{}"
            response_data = json.loads(response_body)
            
            await idempotency_manager.store_response(
                request, tenant_id, idempotency_key, response_data
            )
            
        except Exception as e:
            logger.error("idempotency_store_response_error", 
                        idempotency_key=idempotency_key, 
                        error=str(e))
    
    return response

