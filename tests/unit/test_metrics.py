"""
Unit tests for metrics collection and monitoring.
"""
import pytest
from unittest.mock import Mock, patch

from app.metrics import (
    record_frame_received, record_ack_sent, record_can_frame_processed,
    record_connection_event, set_active_connections, record_database_operation,
    get_metrics
)


class TestMetrics:
    """Test metrics functionality."""
    
    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        """Reset metrics before each test."""
        # Reset all counters and gauges
        from app.metrics import (
            frames_received_total, acks_sent_total, can_frames_processed_total,
            connections_active, database_operations_total, decode_errors_total
        )
        
        # Clear all metrics
        for metric in [frames_received_total, acks_sent_total, can_frames_processed_total,
                      connections_active, database_operations_total, decode_errors_total]:
            metric.clear()
    
    @pytest.mark.unit
    def test_record_frame_received(self):
        """Test frame received metric recording."""
        device_id = "TEST1234"
        frame_size = 100
        data_type = 1
        
        # Record frame
        record_frame_received(device_id, frame_size, data_type)
        
        # Check metric
        from app.metrics import frames_received_total
        assert frames_received_total._value._value == 1
    
    @pytest.mark.unit
    def test_record_ack_sent(self):
        """Test ACK sent metric recording."""
        device_id = "TEST1234"
        ack_type = "ack"
        
        # Record ACK
        record_ack_sent(device_id, ack_type)
        
        # Check metric
        from app.metrics import acks_sent_total
        assert acks_sent_total._value._value == 1
    
    @pytest.mark.unit
    def test_record_can_frame_processed(self):
        """Test CAN frame processed metric recording."""
        device_id = "TEST1234"
        can_id = 0x18F00400
        signal_count = 5
        
        # Record CAN frame
        record_can_frame_processed(device_id, can_id, signal_count)
        
        # Check metric
        from app.metrics import can_frames_processed_total
        assert can_frames_processed_total._value._value == 1
    
    @pytest.mark.unit
    def test_record_connection_event(self):
        """Test connection event metric recording."""
        event_type = "connected"
        ip = "192.168.1.1"
        port = 5221
        
        # Record connection event
        record_connection_event(event_type, ip, port)
        
        # Check metric
        from app.metrics import connection_events_total
        assert connection_events_total._value._value == 1
    
    @pytest.mark.unit
    def test_set_active_connections(self):
        """Test active connections metric setting."""
        count = 5
        
        # Set active connections
        set_active_connections(count)
        
        # Check metric
        from app.metrics import connections_active
        assert connections_active._value == count
    
    @pytest.mark.unit
    def test_record_database_operation(self):
        """Test database operation metric recording."""
        operation = "insert"
        table = "raw_frames"
        duration_ms = 10.5
        
        # Record database operation
        record_database_operation(operation, table, duration_ms)
        
        # Check metric
        from app.metrics import database_operations_total
        assert database_operations_total._value._value == 1
    
    @pytest.mark.unit
    def test_metrics_increment(self):
        """Test metrics increment correctly."""
        device_id = "TEST1234"
        
        # Record multiple frames
        for i in range(5):
            record_frame_received(device_id, 100, 1)
        
        # Check metric
        from app.metrics import frames_received_total
        assert frames_received_total._value._value == 5
    
    @pytest.mark.unit
    def test_metrics_labels(self):
        """Test metrics with different labels."""
        device1 = "DEVICE1"
        device2 = "DEVICE2"
        
        # Record frames for different devices
        record_frame_received(device1, 100, 1)
        record_frame_received(device2, 200, 2)
        
        # Check metric
        from app.metrics import frames_received_total
        assert frames_received_total._value._value == 2
    
    @pytest.mark.unit
    def test_get_metrics(self):
        """Test getting metrics data."""
        # Record some metrics
        record_frame_received("TEST1234", 100, 1)
        record_ack_sent("TEST1234", "ack")
        set_active_connections(3)
        
        # Get metrics
        metrics_data = get_metrics()
        
        # Should contain metric data
        assert isinstance(metrics_data, str)
        assert "frames_received_total" in metrics_data
        assert "acks_sent_total" in metrics_data
        assert "connections_active" in metrics_data
    
    @pytest.mark.unit
    def test_histogram_metrics(self):
        """Test histogram metrics."""
        # Record database operations with different durations
        durations = [1.0, 5.0, 10.0, 15.0, 20.0]
        
        for duration in durations:
            record_database_operation("insert", "raw_frames", duration)
        
        # Check metric
        from app.metrics import database_operation_duration_ms
        assert database_operation_duration_ms._sum._value == sum(durations)
        assert database_operation_duration_ms._count._value == len(durations)
    
    @pytest.mark.unit
    def test_error_metrics(self):
        """Test error metrics."""
        from app.metrics import record_decode_error
        
        # Record decode errors
        record_decode_error("TEST1234", "crc_error", "Invalid CRC")
        record_decode_error("TEST1234", "parse_error", "Parse failed")
        
        # Check metric
        from app.metrics import decode_errors_total
        assert decode_errors_total._value._value == 2
    
    @pytest.mark.unit
    def test_metrics_performance(self):
        """Test metrics performance."""
        import time
        
        device_id = "PERF_TEST"
        
        start_time = time.time()
        
        # Record 1000 metrics
        for i in range(1000):
            record_frame_received(device_id, 100, 1)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be very fast
        assert duration < 0.1
        print(f"Recorded 1000 metrics in {duration:.3f} seconds")
    
    @pytest.mark.unit
    def test_metrics_thread_safety(self):
        """Test metrics thread safety."""
        import threading
        import time
        
        device_id = "THREAD_TEST"
        results = []
        
        def record_metrics():
            for i in range(100):
                record_frame_received(device_id, 100, 1)
                time.sleep(0.001)  # Small delay
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=record_metrics)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check metric
        from app.metrics import frames_received_total
        assert frames_received_total._value._value == 500  # 5 threads * 100 each
    
    @pytest.mark.unit
    def test_metrics_reset(self):
        """Test metrics reset functionality."""
        # Record some metrics
        record_frame_received("TEST1234", 100, 1)
        record_ack_sent("TEST1234", "ack")
        
        # Check metrics are recorded
        from app.metrics import frames_received_total, acks_sent_total
        assert frames_received_total._value._value == 1
        assert acks_sent_total._value._value == 1
        
        # Reset metrics
        frames_received_total.clear()
        acks_sent_total.clear()
        
        # Check metrics are reset
        assert frames_received_total._value._value == 0
        assert acks_sent_total._value._value == 0
    
    @pytest.mark.unit
    def test_metrics_export_format(self):
        """Test metrics export format."""
        # Record some metrics
        record_frame_received("TEST1234", 100, 1)
        record_ack_sent("TEST1234", "ack")
        set_active_connections(3)
        
        # Get metrics
        metrics_data = get_metrics()
        
        # Should be in Prometheus format
        lines = metrics_data.split('\n')
        
        # Check for metric lines
        metric_lines = [line for line in lines if not line.startswith('#') and line.strip()]
        assert len(metric_lines) > 0
        
        # Check format
        for line in metric_lines:
            if line.strip():
                # Should have metric name and value
                assert ' ' in line or '\t' in line
                parts = line.split()
                assert len(parts) >= 2
                assert parts[1].replace('.', '').isdigit()  # Value should be numeric
