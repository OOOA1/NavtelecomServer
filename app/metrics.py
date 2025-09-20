"""Metrics collection for monitoring."""
import time
from typing import Dict, Any
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger()


class MetricsCollector:
    """Collects and stores application metrics."""
    
    def __init__(self):
        self.counters = defaultdict(int)
        self.gauges = defaultdict(float)
        self.histograms = defaultdict(list)
        self.timers = defaultdict(list)
        self.last_reset = time.time()
    
    def increment_counter(self, name: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        self.counters[key] += value
        logger.debug("counter_incremented", name=name, value=value, labels=labels)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric value."""
        key = self._make_key(name, labels)
        self.gauges[key] = value
        logger.debug("gauge_set", name=name, value=value, labels=labels)
    
    def record_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a histogram value."""
        key = self._make_key(name, labels)
        self.histograms[key].append(value)
        # Keep only last 1000 values
        if len(self.histograms[key]) > 1000:
            self.histograms[key] = self.histograms[key][-1000:]
        logger.debug("histogram_recorded", name=name, value=value, labels=labels)
    
    def record_timer(self, name: str, duration: float, labels: Dict[str, str] = None):
        """Record a timer duration."""
        key = self._make_key(name, labels)
        self.timers[key].append(duration)
        # Keep only last 1000 values
        if len(self.timers[key]) > 1000:
            self.timers[key] = self.timers[key][-1000:]
        logger.debug("timer_recorded", name=name, duration=duration, labels=labels)
    
    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a key for metric storage."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics in Prometheus format."""
        metrics = {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {},
            "timers": {}
        }
        
        # Calculate histogram statistics
        for key, values in self.histograms.items():
            if values:
                metrics["histograms"][key] = {
                    "count": len(values),
                    "sum": sum(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values)
                }
        
        # Calculate timer statistics
        for key, values in self.timers.items():
            if values:
                metrics["timers"][key] = {
                    "count": len(values),
                    "sum": sum(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values)
                }
        
        return metrics
    
    def reset(self):
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.timers.clear()
        self.last_reset = time.time()
        logger.info("metrics_reset")


# Global metrics collector
metrics = MetricsCollector()


# Convenience functions
def increment_counter(name: str, value: int = 1, labels: Dict[str, str] = None):
    """Increment a counter metric."""
    metrics.increment_counter(name, value, labels)


def set_gauge(name: str, value: float, labels: Dict[str, str] = None):
    """Set a gauge metric value."""
    metrics.set_gauge(name, value, labels)


def record_histogram(name: str, value: float, labels: Dict[str, str] = None):
    """Record a histogram value."""
    metrics.record_histogram(name, value, labels)


def record_timer(name: str, duration: float, labels: Dict[str, str] = None):
    """Record a timer duration."""
    metrics.record_timer(name, duration, labels)


# Specific metrics for our application
def record_frame_received(device_id: str, frame_size: int, data_type: int):
    """Record frame received metrics."""
    increment_counter("frames_received_total", labels={
        "device_id": device_id,
        "data_type": str(data_type)
    })
    record_histogram("frame_size_bytes", frame_size, labels={
        "device_id": device_id
    })


def record_ack_sent(device_id: str, ack_type: str = "ack"):
    """Record ACK sent metrics."""
    increment_counter("acks_sent_total", labels={
        "device_id": device_id,
        "ack_type": ack_type
    })


def record_can_frame_processed(device_id: str, can_id: int, signals_count: int):
    """Record CAN frame processing metrics."""
    increment_counter("can_frames_processed_total", labels={
        "device_id": device_id,
        "can_id": str(can_id)
    })
    record_histogram("can_signals_per_frame", signals_count, labels={
        "device_id": device_id
    })


def record_database_operation(operation: str, duration: float, success: bool):
    """Record database operation metrics."""
    increment_counter("database_operations_total", labels={
        "operation": operation,
        "success": str(success).lower()
    })
    record_timer("database_operation_duration_seconds", duration, labels={
        "operation": operation
    })


def record_connection_event(event_type: str, client_ip: str):
    """Record connection event metrics."""
    increment_counter("connection_events_total", labels={
        "event_type": event_type,
        "client_ip": client_ip
    })


def set_active_connections(count: int):
    """Set active connections gauge."""
    set_gauge("active_connections", count)


def set_queue_size(queue_name: str, size: int):
    """Set queue size gauge."""
    set_gauge("queue_size", size, labels={"queue": queue_name})
