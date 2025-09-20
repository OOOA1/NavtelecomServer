"""
Unit tests for backpressure management and rate limiting.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock

from app.backpressure import BackpressureManager, RateLimiter


class TestBackpressureManager:
    """Test backpressure manager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create backpressure manager instance."""
        return BackpressureManager(
            max_queue_size=100,
            persist_only_threshold=0.8,
            cleanup_interval_ms=1000
        )
    
    @pytest.mark.unit
    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = BackpressureManager()
        
        assert manager.max_queue_size > 0
        assert 0 < manager.persist_only_threshold < 1
        assert len(manager.queues) == 0
        assert not manager.persist_only_mode
    
    @pytest.mark.unit
    def test_queue_creation(self, manager):
        """Test queue creation."""
        queue = manager.get_or_create_queue("test_queue")
        
        assert queue is not None
        assert "test_queue" in manager.queues
        assert manager.queues["test_queue"] == queue
    
    @pytest.mark.unit
    def test_queue_reuse(self, manager):
        """Test queue reuse."""
        queue1 = manager.get_or_create_queue("test_queue")
        queue2 = manager.get_or_create_queue("test_queue")
        
        assert queue1 == queue2
        assert len(manager.queues) == 1
    
    @pytest.mark.unit
    def test_normal_put(self, manager):
        """Test normal put operation."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Put item
        result = manager.put("test_queue", "test_item", priority="normal")
        
        assert result is True
        assert queue.qsize() == 1
    
    @pytest.mark.unit
    def test_priority_drop(self, manager):
        """Test priority-based dropping."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Fill queue to threshold
        for i in range(int(manager.max_queue_size * manager.persist_only_threshold)):
            manager.put("test_queue", f"item_{i}", priority="normal")
        
        # Try to put low priority item
        result = manager.put("test_queue", "low_priority", priority="low")
        
        # Should be dropped
        assert result is False
        assert queue.qsize() == int(manager.max_queue_size * manager.persist_only_threshold)
    
    @pytest.mark.unit
    def test_high_priority_override(self, manager):
        """Test high priority items override threshold."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Fill queue to threshold
        for i in range(int(manager.max_queue_size * manager.persist_only_threshold)):
            manager.put("test_queue", f"item_{i}", priority="normal")
        
        # Try to put high priority item
        result = manager.put("test_queue", "high_priority", priority="high")
        
        # Should be accepted
        assert result is True
        assert queue.qsize() > int(manager.max_queue_size * manager.persist_only_threshold)
    
    @pytest.mark.unit
    def test_queue_full_drop(self, manager):
        """Test dropping when queue is full."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Fill queue completely
        for i in range(manager.max_queue_size):
            manager.put("test_queue", f"item_{i}", priority="normal")
        
        # Try to put another item
        result = manager.put("test_queue", "overflow", priority="normal")
        
        # Should be dropped
        assert result is False
        assert queue.qsize() == manager.max_queue_size
    
    @pytest.mark.unit
    def test_persist_only_mode(self, manager):
        """Test persist-only mode activation."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Fill queue to trigger persist-only mode
        for i in range(int(manager.max_queue_size * manager.persist_only_threshold) + 1):
            manager.put("test_queue", f"item_{i}", priority="normal")
        
        # Should be in persist-only mode
        assert manager.should_persist_only()
        assert manager.persist_only_mode
    
    @pytest.mark.unit
    def test_persist_only_recovery(self, manager):
        """Test recovery from persist-only mode."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Trigger persist-only mode
        for i in range(int(manager.max_queue_size * manager.persist_only_threshold) + 1):
            manager.put("test_queue", f"item_{i}", priority="normal")
        
        assert manager.persist_only_mode
        
        # Drain queue
        while not queue.empty():
            queue.get_nowait()
        
        # Should recover
        assert not manager.should_persist_only()
        assert not manager.persist_only_mode
    
    @pytest.mark.unit
    def test_get_with_timeout(self, manager):
        """Test get operation with timeout."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Put item
        manager.put("test_queue", "test_item", priority="normal")
        
        # Get item
        item = manager.get("test_queue", timeout=1.0)
        
        assert item == "test_item"
        assert queue.empty()
    
    @pytest.mark.unit
    def test_get_timeout(self, manager):
        """Test get operation timeout."""
        queue = manager.get_or_create_queue("test_queue")
        
        # Try to get from empty queue
        with pytest.raises(asyncio.TimeoutError):
            manager.get("test_queue", timeout=0.1)
    
    @pytest.mark.unit
    def test_system_overload_detection(self, manager):
        """Test system overload detection."""
        # Create multiple queues and fill them
        for i in range(3):
            queue_name = f"queue_{i}"
            for j in range(int(manager.max_queue_size * 0.8)):  # 80% full
                manager.put(queue_name, f"item_{j}", priority="normal")
        
        # Should detect overload
        assert manager.is_system_overloaded()
    
    @pytest.mark.unit
    def test_queue_cleanup(self, manager):
        """Test queue cleanup."""
        # Create and use queues
        manager.get_or_create_queue("queue1")
        manager.get_or_create_queue("queue2")
        
        assert len(manager.queues) == 2
        
        # Cleanup empty queues
        manager.cleanup_empty_queues()
        
        # Should still have queues (they're not empty yet)
        assert len(manager.queues) == 2


class TestRateLimiter:
    """Test rate limiter functionality."""
    
    @pytest.fixture
    def limiter(self):
        """Create rate limiter instance."""
        return RateLimiter(
            requests_per_minute=60,
            burst_size=10,
            cleanup_interval_ms=1000
        )
    
    @pytest.mark.unit
    def test_limiter_initialization(self):
        """Test limiter initialization."""
        limiter = RateLimiter()
        
        assert limiter.requests_per_minute > 0
        assert limiter.burst_size > 0
        assert len(limiter.device_rates) == 0
    
    @pytest.mark.unit
    def test_allowed_request(self, limiter):
        """Test allowed request."""
        device_id = "TEST1234"
        
        # First request should be allowed
        assert limiter.is_allowed(device_id=device_id)
        
        # Should have entry for device
        assert device_id in limiter.device_rates
    
    @pytest.mark.unit
    def test_rate_limit_exceeded(self, limiter):
        """Test rate limit exceeded."""
        device_id = "TEST1234"
        
        # Make many requests quickly
        for _ in range(limiter.burst_size + 1):
            limiter.is_allowed(device_id=device_id)
        
        # Should be rate limited
        assert not limiter.is_allowed(device_id=device_id)
    
    @pytest.mark.unit
    def test_different_devices(self, limiter):
        """Test different devices have separate limits."""
        device1 = "DEVICE1"
        device2 = "DEVICE2"
        
        # Exhaust device1's limit
        for _ in range(limiter.burst_size + 1):
            limiter.is_allowed(device_id=device1)
        
        # Device1 should be limited
        assert not limiter.is_allowed(device_id=device1)
        
        # Device2 should still be allowed
        assert limiter.is_allowed(device_id=device2)
    
    @pytest.mark.unit
    def test_rate_recovery(self, limiter):
        """Test rate limit recovery over time."""
        device_id = "TEST1234"
        
        # Exhaust limit
        for _ in range(limiter.burst_size + 1):
            limiter.is_allowed(device_id=device_id)
        
        # Should be limited
        assert not limiter.is_allowed(device_id=device_id)
        
        # Simulate time passing (mock the time)
        with patch('time.time', return_value=time.time() + 61):  # 61 seconds later
            # Should be allowed again
            assert limiter.is_allowed(device_id=device_id)
    
    @pytest.mark.unit
    def test_connection_rate_limit(self, limiter):
        """Test connection rate limiting."""
        # Test connection rate limiting
        for _ in range(limiter.connection_rate_limit + 1):
            limiter.is_allowed(device_id="NEW_DEVICE", is_connection=True)
        
        # Should be limited for new connections
        assert not limiter.is_allowed(device_id="ANOTHER_DEVICE", is_connection=True)
    
    @pytest.mark.unit
    def test_cleanup_old_entries(self, limiter):
        """Test cleanup of old entries."""
        device_id = "OLD_DEVICE"
        
        # Add old entry
        limiter.device_rates[device_id] = [0]  # Very old timestamp
        
        # Trigger cleanup
        limiter._cleanup_old_entries(time.time())
        
        # Old entry should be removed
        assert device_id not in limiter.device_rates
    
    @pytest.mark.unit
    def test_limiter_performance(self, limiter):
        """Test limiter performance."""
        import time
        
        device_id = "PERF_TEST"
        
        start_time = time.time()
        
        # Check rate limit 1000 times
        for _ in range(1000):
            limiter.is_allowed(device_id=device_id)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be very fast
        assert duration < 0.1
        print(f"Rate limited 1000 requests in {duration:.3f} seconds")


class TestBackpressureIntegration:
    """Test backpressure and rate limiting integration."""
    
    @pytest.mark.unit
    def test_backpressure_with_rate_limiting(self):
        """Test backpressure manager with rate limiting."""
        manager = BackpressureManager(max_queue_size=10)
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        device_id = "TEST1234"
        
        # Exhaust rate limit
        for _ in range(limiter.burst_size + 1):
            limiter.is_allowed(device_id=device_id)
        
        # Should be rate limited
        assert not limiter.is_allowed(device_id=device_id)
        
        # Backpressure should still work
        queue = manager.get_or_create_queue(device_id)
        result = manager.put(device_id, "test_item", priority="normal")
        
        # Should be accepted by backpressure manager
        assert result is True
        assert queue.qsize() == 1
    
    @pytest.mark.unit
    def test_combined_stress_test(self):
        """Test combined stress scenario."""
        manager = BackpressureManager(max_queue_size=100, persist_only_threshold=0.8)
        limiter = RateLimiter(requests_per_minute=1000, burst_size=100)
        
        device_id = "STRESS_TEST"
        
        # Simulate high load
        accepted = 0
        rejected = 0
        
        for i in range(200):
            # Check rate limit
            if not limiter.is_allowed(device_id=device_id):
                rejected += 1
                continue
            
            # Try to put in queue
            if manager.put(device_id, f"item_{i}", priority="normal"):
                accepted += 1
            else:
                rejected += 1
        
        # Should have some accepted and some rejected
        assert accepted > 0
        assert rejected > 0
        assert accepted + rejected == 200
        
        print(f"Stress test: {accepted} accepted, {rejected} rejected")


# Mock time for testing
@pytest.fixture(autouse=True)
def mock_time():
    """Mock time for consistent testing."""
    with patch('time.time', return_value=1000.0):
        yield
