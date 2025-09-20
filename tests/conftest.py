"""
Pytest configuration and shared fixtures.
"""
import pytest
import asyncio
import os
import tempfile
import time
import struct
from typing import Dict, Any, AsyncGenerator
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone

# Set test environment
os.environ["TESTING"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_settings():
    """Test settings configuration."""
    return {
        "tcp_host": "127.0.0.1",
        "tcp_port": 15221,
        "api_host": "127.0.0.1", 
        "api_port": 18080,
        "database_url": "postgresql+asyncpg://postgres:postgres@localhost:15432/navtel_test",
        "log_level": "WARNING",
        "can_raw_enable": True,
        "can_decode_enable": True,
        "can_max_frame_rate": 1000,
        "can_tp_assemble_timeout_ms": 5000,
        "api_key": "test-api-key-12345",
        "jwt_secret": "test-jwt-secret-key",
        "hmac_secret": "test-hmac-secret-key",
        "backpressure_max_queue_size": 1000,
        "backpressure_persist_only_threshold": 0.8,
        "rate_limit_requests_per_minute": 1000,
        "retention_days": 7,
        "archive_enabled": False
    }

@pytest.fixture
def mock_database():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    return session

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=False)
    return redis

@pytest.fixture
def mock_clock():
    """Mock clock for time-dependent tests."""
    clock = Mock()
    clock.now = Mock(return_value=datetime(2025, 9, 20, 12, 0, 0, tzinfo=timezone.utc))
    clock.time = Mock(return_value=1726826400.0)
    return clock

@pytest.fixture
def test_device_id():
    """Test device ID."""
    return "TEST123456789"

@pytest.fixture
def test_can_frame():
    """Test CAN frame data."""
    return {
        "can_id": 0x18F00400,
        "payload": b"\x00\x80\x00\x00\x00\x00\x00\x00",
        "dlc": 8,
        "is_extended": True,
        "timestamp": 1726826400.0
    }

@pytest.fixture
def test_gps_frame():
    """Test GPS frame data."""
    return {
        "device_id": "TEST123456789",
        "lat": 55.7558,
        "lon": 37.6176,
        "speed": 50.0,
        "course": 180.0,
        "timestamp": 1726826400.0
    }

@pytest.fixture
def test_navtelecom_frame():
    """Test Navtelecom protocol frame."""
    device_id = "TEST1234"
    timestamp = int(time.time())
    data_type = 1
    # Create proper GPS payload (20 bytes as expected by parse_gps_data)
    payload = struct.pack('<dddd', 55.7558, 37.6176, 50.0, 180.0)  # lat, lon, speed, course
    
    # Build frame data
    frame_data = device_id.encode('ascii').ljust(8, b'\x00')[:8]
    frame_data += timestamp.to_bytes(4, 'little')
    frame_data += data_type.to_bytes(1, 'little')
    frame_data += payload
    
    # Calculate CRC
    crc = 0xFFFF
    for byte in frame_data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    
    # Build complete frame
    frame = bytearray()
    frame.append(0x7E)  # Start marker
    frame.extend(len(frame_data).to_bytes(2, 'little'))  # Length
    frame.extend(frame_data)  # Data
    frame.extend(crc.to_bytes(2, 'little'))  # CRC
    frame.append(0x7E)  # End marker
    
    return bytes(frame)

@pytest.fixture
def test_j1939_frame():
    """Test J1939 CAN frame."""
    return {
        "can_id": 0x18F00400,  # Engine speed PGN
        "payload": b"\x00\x80",  # 1000 RPM
        "pgn": 0xF004,
        "spn": 190,
        "expected_signals": [
            {
                "name": "EngineRPM",
                "value": 1000.0,
                "unit": "rpm"
            }
        ]
    }

@pytest.fixture
def test_obd2_frame():
    """Test OBD-II CAN frame."""
    return {
        "can_id": 0x7E8,  # OBD-II response
        "payload": b"\x41\x0C\x00\x80",  # Mode 01, PID 0C, 1000 RPM
        "mode": 0x41,
        "pid": 0x0C,
        "expected_signals": [
            {
                "name": "EngineRPM",
                "value": 1000.0,
                "unit": "rpm"
            }
        ]
    }

@pytest.fixture
def test_tp_bam_frame():
    """Test J1939 BAM (Broadcast Announce Message) frame."""
    return {
        "can_id": 0x18ECFF00,  # BAM PGN
        "payload": b"\x20\x00\x10\x01\x01\x02\x03\x04",  # BAM with data
        "sequence": 1,
        "total_packets": 2,
        "data": b"\x01\x02\x03\x04"
    }

@pytest.fixture
def test_tp_rts_frame():
    """Test J1939 RTS (Request to Send) frame."""
    return {
        "can_id": 0x18ECFF00,  # RTS PGN
        "payload": b"\x10\x00\x10\x00\x00\x00\x00\x00",  # RTS
        "sequence": 1,
        "total_packets": 2,
        "data_size": 16
    }

@pytest.fixture
def test_tp_cts_frame():
    """Test J1939 CTS (Clear to Send) frame."""
    return {
        "can_id": 0x18ECFF00,  # CTS PGN
        "payload": b"\x11\x00\x10\x00\x00\x00\x00\x00",  # CTS
        "sequence": 1,
        "packets_to_send": 2
    }

@pytest.fixture
def temp_dict_file():
    """Temporary dictionary file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("""
pgns:
  "61444":
    name: "Engine Speed"
    signals:
      - spn: 190
        name: "EngineRPM"
        start_bit: 0
        length: 16
        scale: 0.125
        offset: 0.0
        unit: "rpm"
        byte_order: "little"
""")
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    try:
        os.unlink(temp_file)
    except OSError:
        pass

@pytest.fixture
def mock_metrics():
    """Mock metrics collector."""
    metrics = Mock()
    metrics.record_frame_received = Mock()
    metrics.record_ack_sent = Mock()
    metrics.record_can_frame_processed = Mock()
    metrics.record_connection_event = Mock()
    metrics.set_active_connections = Mock()
    metrics.record_database_operation = Mock()
    return metrics

@pytest.fixture
def mock_alert_manager():
    """Mock alert manager."""
    alert_manager = Mock()
    alert_manager.check_alerts = Mock()
    alert_manager.raise_alert = Mock()
    alert_manager.resolve_alert = Mock()
    alert_manager.get_active_alerts = Mock(return_value=[])
    return alert_manager

@pytest.fixture
def mock_slo_manager():
    """Mock SLO manager."""
    slo_manager = Mock()
    slo_manager.record_measurement = Mock()
    slo_manager.get_current_slo_status = Mock(return_value={"status": "healthy"})
    slo_manager.check_burn_rate = Mock(return_value={"alert_1h": False, "alert_6h": False})
    return slo_manager

# Test markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no I/O)")
    config.addinivalue_line("markers", "api: API tests (FastAPI, mocked dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (real DB/Redis)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full system)")
    config.addinivalue_line("markers", "slow: Slow tests (>1s)")
    config.addinivalue_line("markers", "smoke: Smoke tests (quick health checks)")
    config.addinivalue_line("markers", "load: Load tests")
    config.addinivalue_line("markers", "chaos: Chaos engineering tests")

# Async test support
@pytest.fixture
def async_client():
    """Async HTTP client for API tests."""
    import httpx
    return httpx.AsyncClient()

# Database fixtures for integration tests
@pytest.fixture
async def test_db_session():
    """Test database session for integration tests."""
    from app.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()

# Cleanup fixtures
@pytest.fixture(autouse=True)
def cleanup_test_data():
    """Cleanup test data after each test."""
    yield
    # Add cleanup logic here if needed
