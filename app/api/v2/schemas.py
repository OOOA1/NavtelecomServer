"""
API v2 schemas and models.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class DeviceStatus(str, Enum):
    """Device status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class SignalType(str, Enum):
    """Signal type enumeration."""
    CAN = "can"
    GPS = "gps"
    SENSOR = "sensor"
    DIAGNOSTIC = "diagnostic"


# Base models
class BaseResponse(BaseModel):
    """Base response model."""
    trace_id: str = Field(..., description="Request trace ID")


class ErrorResponse(BaseResponse):
    """Error response model."""
    error: Dict[str, Any] = Field(..., description="Error details")


class SuccessResponse(BaseResponse):
    """Success response model."""
    data: Any = Field(..., description="Response data")
    meta: Optional[Dict[str, Any]] = Field(None, description="Metadata")


# Device models
class DeviceInfo(BaseModel):
    """Device information model."""
    id: str = Field(..., description="Device ID")
    name: Optional[str] = Field(None, description="Device name")
    status: DeviceStatus = Field(..., description="Device status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class DeviceListResponse(SuccessResponse):
    """Device list response."""
    data: List[DeviceInfo] = Field(..., description="List of devices")
    next_cursor: Optional[str] = Field(None, description="Next page cursor")


# CAN signal models (v2 improvements)
class CANSignal(BaseModel):
    """CAN signal model (v2)."""
    id: str = Field(..., description="Signal ID")
    device_id: str = Field(..., description="Device ID")
    time: datetime = Field(..., description="Signal timestamp (RFC3339Z)")
    pgn: Optional[int] = Field(None, description="Parameter Group Number")
    spn: Optional[int] = Field(None, description="Suspect Parameter Number")
    value: Any = Field(..., description="Signal value")
    unit: Optional[str] = Field(None, description="Signal unit")
    raw_data: Optional[str] = Field(None, description="Raw CAN data")
    dict_version: Optional[str] = Field(None, description="Dictionary version")


class CANSignalListResponse(SuccessResponse):
    """CAN signal list response (v2)."""
    data: List[CANSignal] = Field(..., description="List of CAN signals")
    next_cursor: Optional[str] = Field(None, description="Next page cursor")
    meta: Dict[str, Any] = Field(..., description="Metadata including total_estimate")


# Raw frame models
class RawFrame(BaseModel):
    """Raw frame model."""
    id: str = Field(..., description="Frame ID")
    device_id: str = Field(..., description="Device ID")
    received_at: datetime = Field(..., description="Received timestamp")
    payload: str = Field(..., description="Frame payload")
    frame_type: Optional[str] = Field(None, description="Frame type")


class RawFrameListResponse(SuccessResponse):
    """Raw frame list response."""
    data: List[RawFrame] = Field(..., description="List of raw frames")
    next_cursor: Optional[str] = Field(None, description="Next page cursor")


# Telemetry models
class TelemetryData(BaseModel):
    """Telemetry data model."""
    id: str = Field(..., description="Telemetry ID")
    device_id: str = Field(..., description="Device ID")
    received_at: datetime = Field(..., description="Received timestamp")
    data: Dict[str, Any] = Field(..., description="Telemetry data")
    signal_type: SignalType = Field(..., description="Signal type")


class TelemetryListResponse(SuccessResponse):
    """Telemetry list response."""
    data: List[TelemetryData] = Field(..., description="List of telemetry data")
    next_cursor: Optional[str] = Field(None, description="Next page cursor")


# Filter DSL for v2
class FilterCondition(BaseModel):
    """Filter condition."""
    field: str = Field(..., description="Field name")
    operator: str = Field(..., description="Operator (eq, ne, gt, lt, gte, lte, in, contains)")
    value: Union[str, int, float, List[Any]] = Field(..., description="Filter value")


class FilterDSL(BaseModel):
    """Filter DSL for complex queries."""
    conditions: List[FilterCondition] = Field(..., description="Filter conditions")
    logic: str = Field("AND", description="Logic operator (AND, OR)")


# Query parameters (v2 improvements)
class PaginationParams(BaseModel):
    """Pagination parameters."""
    cursor: Optional[str] = Field(None, description="Page cursor")
    limit: int = Field(100, ge=1, le=1000, description="Page size")


class TimeRangeParams(BaseModel):
    """Time range parameters."""
    from_time: Optional[datetime] = Field(None, description="Start time")
    to_time: Optional[datetime] = Field(None, description="End time")


class CANSignalQueryParams(TimeRangeParams, PaginationParams):
    """CAN signal query parameters (v2)."""
    filter: Optional[FilterDSL] = Field(None, description="Filter DSL")
    device_id: Optional[str] = Field(None, description="Device ID filter")
    include_metadata: bool = Field(False, description="Include metadata in response")


class RawFrameQueryParams(TimeRangeParams, PaginationParams):
    """Raw frame query parameters."""
    device_id: Optional[str] = Field(None, description="Device ID filter")
    frame_type: Optional[str] = Field(None, description="Frame type filter")


class TelemetryQueryParams(TimeRangeParams, PaginationParams):
    """Telemetry query parameters."""
    device_id: Optional[str] = Field(None, description="Device ID filter")
    signal_type: Optional[SignalType] = Field(None, description="Signal type filter")


# Health check models
class HealthStatus(BaseModel):
    """Health status model."""
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Check timestamp")
    version: str = Field(..., description="API version")
    uptime: int = Field(..., description="Uptime in seconds")


class HealthResponse(BaseResponse):
    """Health response model."""
    data: HealthStatus = Field(..., description="Health status data")

