"""
API v1 schemas and models.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
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


# CAN signal models
class CANSignal(BaseModel):
    """CAN signal model."""
    id: str = Field(..., description="Signal ID")
    device_id: str = Field(..., description="Device ID")
    signal_time: datetime = Field(..., description="Signal timestamp")
    pgn: Optional[int] = Field(None, description="Parameter Group Number")
    spn: Optional[int] = Field(None, description="Suspect Parameter Number")
    value: Any = Field(..., description="Signal value")
    unit: Optional[str] = Field(None, description="Signal unit")
    raw_data: Optional[str] = Field(None, description="Raw CAN data")


class CANSignalListResponse(SuccessResponse):
    """CAN signal list response."""
    data: List[CANSignal] = Field(..., description="List of CAN signals")
    next_cursor: Optional[str] = Field(None, description="Next page cursor")


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


# Query parameters
class PaginationParams(BaseModel):
    """Pagination parameters."""
    cursor: Optional[str] = Field(None, description="Page cursor")
    limit: int = Field(100, ge=1, le=1000, description="Page size")


class TimeRangeParams(BaseModel):
    """Time range parameters."""
    from_time: Optional[datetime] = Field(None, description="Start time")
    to_time: Optional[datetime] = Field(None, description="End time")


class CANSignalQueryParams(TimeRangeParams, PaginationParams):
    """CAN signal query parameters."""
    pgn: Optional[int] = Field(None, description="Parameter Group Number")
    spn: Optional[int] = Field(None, description="Suspect Parameter Number")
    device_id: Optional[str] = Field(None, description="Device ID filter")


class RawFrameQueryParams(TimeRangeParams, PaginationParams):
    """Raw frame query parameters."""
    device_id: Optional[str] = Field(None, description="Device ID filter")
    frame_type: Optional[str] = Field(None, description="Frame type filter")


class TelemetryQueryParams(TimeRangeParams, PaginationParams):
    """Telemetry query parameters."""
    device_id: Optional[str] = Field(None, description="Device ID filter")
    signal_type: Optional[SignalType] = Field(None, description="Signal type filter")

