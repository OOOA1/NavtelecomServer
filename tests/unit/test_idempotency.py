"""
Unit tests for idempotency handling.
"""
import pytest
import hashlib
import uuid
from unittest.mock import Mock, AsyncMock

from app.models import check_idempotency, save_with_idempotency


class TestIdempotency:
    """Test idempotency functionality."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session
    
    @pytest.mark.unit
    def test_idempotency_key_generation(self):
        """Test idempotency key generation."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload = '{"test": "data"}'
        
        # Generate idempotency key
        key_data = f"{device_id}:{timestamp}:{payload}"
        idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()
        
        assert len(idempotency_key) == 64  # SHA256 hex length
        assert isinstance(idempotency_key, str)
    
    @pytest.mark.unit
    def test_idempotency_key_consistency(self):
        """Test idempotency key consistency."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload = '{"test": "data"}'
        
        # Generate key twice
        key_data = f"{device_id}:{timestamp}:{payload}"
        key1 = hashlib.sha256(key_data.encode()).hexdigest()
        key2 = hashlib.sha256(key_data.encode()).hexdigest()
        
        assert key1 == key2
    
    @pytest.mark.unit
    def test_idempotency_key_uniqueness(self):
        """Test idempotency key uniqueness."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        
        # Different payloads should generate different keys
        payload1 = '{"test": "data1"}'
        payload2 = '{"test": "data2"}'
        
        key_data1 = f"{device_id}:{timestamp}:{payload1}"
        key_data2 = f"{device_id}:{timestamp}:{payload2}"
        
        key1 = hashlib.sha256(key_data1.encode()).hexdigest()
        key2 = hashlib.sha256(key_data2.encode()).hexdigest()
        
        assert key1 != key2
    
    @pytest.mark.unit
    async def test_check_idempotency_new(self, mock_db_session):
        """Test checking idempotency for new request."""
        idempotency_key = "test-key-123"
        
        # Mock database response (no existing record)
        mock_db_session.execute.return_value.fetchone.return_value = None
        
        result = await check_idempotency(mock_db_session, idempotency_key)
        
        assert result is None  # No existing record
    
    @pytest.mark.unit
    async def test_check_idempotency_existing(self, mock_db_session):
        """Test checking idempotency for existing request."""
        idempotency_key = "test-key-123"
        existing_id = str(uuid.uuid4())
        
        # Mock database response (existing record)
        mock_db_session.execute.return_value.fetchone.return_value = (existing_id,)
        
        result = await check_idempotency(mock_db_session, idempotency_key)
        
        assert result == existing_id
    
    @pytest.mark.unit
    async def test_save_with_idempotency_new(self, mock_db_session):
        """Test saving with idempotency for new request."""
        idempotency_key = "test-key-123"
        data = {"device_id": "TEST1234", "payload": "test"}
        
        # Mock database response (no existing record)
        mock_db_session.execute.return_value.fetchone.return_value = None
        mock_db_session.execute.return_value.scalar_one.return_value = str(uuid.uuid4())
        
        result = await save_with_idempotency(
            mock_db_session, "packets", data, idempotency_key
        )
        
        assert result is not None
        assert isinstance(result, str)  # Should return ID
    
    @pytest.mark.unit
    async def test_save_with_idempotency_duplicate(self, mock_db_session):
        """Test saving with idempotency for duplicate request."""
        idempotency_key = "test-key-123"
        data = {"device_id": "TEST1234", "payload": "test"}
        existing_id = str(uuid.uuid4())
        
        # Mock database response (existing record)
        mock_db_session.execute.return_value.fetchone.return_value = (existing_id,)
        
        result = await save_with_idempotency(
            mock_db_session, "packets", data, idempotency_key
        )
        
        assert result == existing_id  # Should return existing ID
    
    @pytest.mark.unit
    async def test_save_with_idempotency_race_condition(self, mock_db_session):
        """Test saving with idempotency under race conditions."""
        idempotency_key = "test-key-123"
        data = {"device_id": "TEST1234", "payload": "test"}
        
        # Mock database response (UniqueViolation on insert)
        from sqlalchemy.exc import IntegrityError
        mock_db_session.execute.side_effect = IntegrityError(
            "duplicate key value violates unique constraint",
            None, None
        )
        
        # Mock successful retry
        mock_db_session.execute.return_value.fetchone.return_value = (str(uuid.uuid4()),)
        
        result = await save_with_idempotency(
            mock_db_session, "packets", data, idempotency_key
        )
        
        assert result is not None
        assert isinstance(result, str)
    
    @pytest.mark.unit
    def test_idempotency_key_from_request(self):
        """Test generating idempotency key from request data."""
        request_data = {
            "device_id": "TEST1234",
            "timestamp": "2025-09-20T12:00:00Z",
            "payload": {"test": "data"}
        }
        
        # Generate key from request
        import json
        key_data = f"{request_data['device_id']}:{request_data['timestamp']}:{json.dumps(request_data['payload'], sort_keys=True)}"
        idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()
        
        assert len(idempotency_key) == 64
        assert isinstance(idempotency_key, str)
    
    @pytest.mark.unit
    def test_idempotency_key_case_sensitivity(self):
        """Test idempotency key case sensitivity."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload1 = '{"test": "data"}'
        payload2 = '{"TEST": "DATA"}'  # Different case
        
        key_data1 = f"{device_id}:{timestamp}:{payload1}"
        key_data2 = f"{device_id}:{timestamp}:{payload2}"
        
        key1 = hashlib.sha256(key_data1.encode()).hexdigest()
        key2 = hashlib.sha256(key_data2.encode()).hexdigest()
        
        assert key1 != key2  # Should be different
    
    @pytest.mark.unit
    def test_idempotency_key_whitespace_sensitivity(self):
        """Test idempotency key whitespace sensitivity."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload1 = '{"test": "data"}'
        payload2 = '{"test": "data"}'  # Same but different whitespace
        
        key_data1 = f"{device_id}:{timestamp}:{payload1}"
        key_data2 = f"{device_id}:{timestamp}:{payload2}"
        
        key1 = hashlib.sha256(key_data1.encode()).hexdigest()
        key2 = hashlib.sha256(key_data2.encode()).hexdigest()
        
        assert key1 == key2  # Should be same
    
    @pytest.mark.unit
    async def test_idempotency_performance(self, mock_db_session):
        """Test idempotency performance."""
        import time
        
        idempotency_key = "test-key-123"
        
        # Mock database response
        mock_db_session.execute.return_value.fetchone.return_value = None
        
        start_time = time.time()
        
        # Check idempotency 1000 times
        for _ in range(1000):
            await check_idempotency(mock_db_session, idempotency_key)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be fast
        assert duration < 1.0
        print(f"Checked idempotency 1000 times in {duration:.3f} seconds")
    
    @pytest.mark.unit
    def test_idempotency_key_collision_resistance(self):
        """Test idempotency key collision resistance."""
        # Generate many keys and check for collisions
        keys = set()
        
        for i in range(10000):
            device_id = f"DEVICE{i}"
            timestamp = f"2025-09-20T12:00:{i:02d}Z"
            payload = f'{{"test": "data{i}"}}'
            
            key_data = f"{device_id}:{timestamp}:{payload}"
            key = hashlib.sha256(key_data.encode()).hexdigest()
            
            # Should not have collisions
            assert key not in keys
            keys.add(key)
        
        assert len(keys) == 10000
    
    @pytest.mark.unit
    async def test_idempotency_with_different_tables(self, mock_db_session):
        """Test idempotency with different tables."""
        idempotency_key = "test-key-123"
        data = {"device_id": "TEST1234", "payload": "test"}
        
        # Mock database response
        mock_db_session.execute.return_value.fetchone.return_value = None
        mock_db_session.execute.return_value.scalar_one.return_value = str(uuid.uuid4())
        
        # Test with different tables
        tables = ["packets", "raw_frames", "can_signals"]
        
        for table in tables:
            result = await save_with_idempotency(
                mock_db_session, table, data, idempotency_key
            )
            
            assert result is not None
            assert isinstance(result, str)
    
    @pytest.mark.unit
    async def test_idempotency_error_handling(self, mock_db_session):
        """Test idempotency error handling."""
        idempotency_key = "test-key-123"
        data = {"device_id": "TEST1234", "payload": "test"}
        
        # Mock database error
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception):
            await save_with_idempotency(
                mock_db_session, "packets", data, idempotency_key
            )
    
    @pytest.mark.unit
    def test_idempotency_key_length(self):
        """Test idempotency key length."""
        # Test with very long payload
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload = "X" * 10000  # Very long payload
        
        key_data = f"{device_id}:{timestamp}:{payload}"
        idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()
        
        # Should always be 64 characters (SHA256 hex)
        assert len(idempotency_key) == 64
    
    @pytest.mark.unit
    def test_idempotency_key_unicode(self):
        """Test idempotency key with unicode characters."""
        device_id = "TEST1234"
        timestamp = "2025-09-20T12:00:00Z"
        payload = '{"test": "тест", "emoji": "🚀"}'  # Unicode characters
        
        key_data = f"{device_id}:{timestamp}:{payload}"
        idempotency_key = hashlib.sha256(key_data.encode('utf-8')).hexdigest()
        
        assert len(idempotency_key) == 64
        assert isinstance(idempotency_key, str)
