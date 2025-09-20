"""
API v2 device endpoints with improved features.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.api.deps import get_tenant_from_api_key, get_trace_id, check_rate_limit
from app.api.v2.schemas import (
    DeviceInfo, DeviceListResponse, PaginationParams, SuccessResponse,
    CANSignalQueryParams, FilterDSL
)
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/devices", tags=["devices-v2"])


@router.get("/", response_model=DeviceListResponse)
async def list_devices(
    cursor: Optional[str] = Query(None, description="Page cursor"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    tenant: dict = Depends(get_tenant_from_api_key),
    trace_id: str = Depends(get_trace_id)
):
    """List devices for tenant (v2)."""
    
    # Check rate limits
    await check_rate_limit(tenant, None)
    
    try:
        async with AsyncSessionLocal() as session:
            # Set tenant context
            await session.execute(
                text("SELECT set_tenant_context(:tenant_id)"),
                {"tenant_id": tenant["id"]}
            )
            
            # Build query
            query = """
                SELECT id, device_id, device_name, status, created_at, updated_at
                FROM tenant_devices
                WHERE tenant_id = :tenant_id
            """
            params = {"tenant_id": tenant["id"]}
            
            # Add cursor-based pagination
            if cursor:
                query += " AND id > :cursor"
                params["cursor"] = cursor
            
            query += " ORDER BY id LIMIT :limit"
            params["limit"] = limit + 1  # Get one extra to check if there's a next page
            
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            # Process results
            devices = []
            next_cursor = None
            
            for i, row in enumerate(rows):
                if i >= limit:
                    next_cursor = row[0]  # Use ID as cursor
                    break
                
                devices.append(DeviceInfo(
                    id=row[1],  # device_id
                    name=row[2],  # device_name
                    status=row[3],  # status
                    created_at=row[4],  # created_at
                    updated_at=row[5]   # updated_at
                ))
            
            return DeviceListResponse(
                data=devices,
                next_cursor=next_cursor,
                trace_id=trace_id
            )
            
    except Exception as e:
        logger.error("list_devices_v2_error", tenant_id=tenant["id"], error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list devices"
        )


@router.get("/{device_id}", response_model=SuccessResponse)
async def get_device(
    device_id: str,
    tenant: dict = Depends(get_tenant_from_api_key),
    trace_id: str = Depends(get_trace_id)
):
    """Get device information (v2)."""
    
    # Check rate limits
    await check_rate_limit(tenant, None)
    
    try:
        async with AsyncSessionLocal() as session:
            # Set tenant context
            await session.execute(
                text("SELECT set_tenant_context(:tenant_id)"),
                {"tenant_id": tenant["id"]}
            )
            
            # Get device
            result = await session.execute(
                text("""
                    SELECT id, device_id, device_name, status, created_at, updated_at
                    FROM tenant_devices
                    WHERE tenant_id = :tenant_id AND device_id = :device_id
                """),
                {
                    "tenant_id": tenant["id"],
                    "device_id": device_id
                }
            )
            
            row = result.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Device not found"
                )
            
            device = DeviceInfo(
                id=row[1],  # device_id
                name=row[2],  # device_name
                status=row[3],  # status
                created_at=row[4],  # created_at
                updated_at=row[5]   # updated_at
            )
            
            return SuccessResponse(
                data=device,
                trace_id=trace_id
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_device_v2_error", device_id=device_id, tenant_id=tenant["id"], error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get device"
        )


@router.get("/{device_id}/can/signals", response_model=SuccessResponse)
async def get_device_can_signals(
    device_id: str,
    from_time: Optional[str] = Query(None, description="Start time"),
    to_time: Optional[str] = Query(None, description="End time"),
    filter: Optional[str] = Query(None, description="Filter DSL (JSON)"),
    cursor: Optional[str] = Query(None, description="Page cursor"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    include_metadata: bool = Query(False, description="Include metadata"),
    tenant: dict = Depends(get_tenant_from_api_key),
    trace_id: str = Depends(get_trace_id)
):
    """Get CAN signals for device (v2 with improved filtering)."""
    
    # Check rate limits
    await check_rate_limit(tenant, None)
    
    try:
        async with AsyncSessionLocal() as session:
            # Set tenant context
            await session.execute(
                text("SELECT set_tenant_context(:tenant_id)"),
                {"tenant_id": tenant["id"]}
            )
            
            # Build query
            query = """
                SELECT id, device_id, signal_time, pgn, spn, value, unit, raw_data
                FROM can_signals
                WHERE tenant_id = :tenant_id AND device_id = :device_id
            """
            params = {
                "tenant_id": tenant["id"],
                "device_id": device_id
            }
            
            # Add time filters
            if from_time:
                query += " AND signal_time >= :from_time"
                params["from_time"] = from_time
            
            if to_time:
                query += " AND signal_time <= :to_time"
                params["to_time"] = to_time
            
            # Add filter DSL support
            if filter:
                # Parse filter DSL and apply conditions
                # This is a simplified implementation
                import json
                try:
                    filter_data = json.loads(filter)
                    if "conditions" in filter_data:
                        for condition in filter_data["conditions"]:
                            field = condition.get("field")
                            operator = condition.get("operator")
                            value = condition.get("value")
                            
                            if field == "pgn" and operator == "eq":
                                query += " AND pgn = :filter_pgn"
                                params["filter_pgn"] = value
                            elif field == "spn" and operator == "eq":
                                query += " AND spn = :filter_spn"
                                params["filter_spn"] = value
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid filter DSL format"
                    )
            
            # Add cursor-based pagination
            if cursor:
                query += " AND id > :cursor"
                params["cursor"] = cursor
            
            query += " ORDER BY id LIMIT :limit"
            params["limit"] = limit + 1  # Get one extra to check if there's a next page
            
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            # Process results
            signals = []
            next_cursor = None
            
            for i, row in enumerate(rows):
                if i >= limit:
                    next_cursor = row[0]  # Use ID as cursor
                    break
                
                # v2 uses 'time' instead of 'signal_time' and includes dict_version
                signals.append({
                    "id": row[0],
                    "device_id": row[1],
                    "time": row[2],  # Changed from signal_time
                    "pgn": row[3],
                    "spn": row[4],
                    "value": row[5],
                    "unit": row[6],
                    "raw_data": row[7],
                    "dict_version": "v2.0"  # v2 addition
                })
            
            # Build response with metadata
            response_data = {
                "items": signals,
                "next_cursor": next_cursor
            }
            
            if include_metadata:
                # Get total estimate
                count_query = query.replace("ORDER BY id LIMIT :limit", "")
                count_result = await session.execute(text(count_query), params)
                total_estimate = len(count_result.fetchall())
                
                response_data["meta"] = {
                    "total_estimate": total_estimate,
                    "dict_version": "v2.0"
                }
            
            return SuccessResponse(
                data=response_data,
                trace_id=trace_id
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_device_can_signals_v2_error", 
                    device_id=device_id, 
                    tenant_id=tenant["id"], 
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get CAN signals"
        )


@router.get("/health", response_model=SuccessResponse)
async def health_check(
    trace_id: str = Depends(get_trace_id)
):
    """Health check endpoint (v2)."""
    
    from datetime import datetime, timezone
    import time
    
    # Get uptime (simplified)
    uptime = int(time.time() - start_time) if 'start_time' in globals() else 0
    
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc),
        "version": "v2",
        "uptime": uptime
    }
    
    return SuccessResponse(
        data=health_data,
        trace_id=trace_id
    )

