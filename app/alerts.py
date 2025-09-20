"""Alerting and monitoring system."""
import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Alert definition."""
    name: str
    severity: AlertSeverity
    message: str
    timestamp: float
    labels: Dict[str, str]
    value: float
    threshold: float


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.rules: Dict[str, Dict[str, Any]] = {
            "no_frames_5m": {
                "enabled": True,
                "severity": AlertSeverity.WARNING,
                "threshold": 300,  # 5 minutes
                "message": "No frames received for {threshold} seconds"
            },
            "decode_error_rate": {
                "enabled": True,
                "severity": AlertSeverity.ERROR,
                "threshold": 5.0,  # 5%
                "message": "Decode error rate is {value}% (threshold: {threshold}%)"
            },
            "queue_length": {
                "enabled": True,
                "severity": AlertSeverity.WARNING,
                "threshold": 1000,
                "message": "Queue length is {value} (threshold: {threshold})"
            },
            "database_errors": {
                "enabled": True,
                "severity": AlertSeverity.ERROR,
                "threshold": 10,
                "message": "Database errors: {value} (threshold: {threshold})"
            },
            "high_latency": {
                "enabled": True,
                "severity": AlertSeverity.WARNING,
                "threshold": 1000,  # 1 second
                "message": "High latency: {value}ms (threshold: {threshold}ms)"
            }
        }
        self.running = False
        self.check_interval = 60  # 1 minute
        self.last_check = time.time()
        self.metrics_history: Dict[str, List[float]] = {}
    
    async def start(self):
        """Start alert manager."""
        self.running = True
        asyncio.create_task(self._check_loop())
        logger.info("alert_manager_started")
    
    async def stop(self):
        """Stop alert manager."""
        self.running = False
        logger.info("alert_manager_stopped")
    
    async def _check_loop(self):
        """Main alert checking loop."""
        while self.running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_alerts()
            except Exception as e:
                logger.error("alert_check_loop_error", error=str(e))
    
    async def _check_alerts(self):
        """Check all alert rules."""
        current_time = time.time()
        
        # Check each rule
        for rule_name, rule_config in self.rules.items():
            if not rule_config["enabled"]:
                continue
            
            try:
                await self._check_rule(rule_name, rule_config, current_time)
            except Exception as e:
                logger.error("rule_check_error", rule=rule_name, error=str(e))
        
        self.last_check = current_time
    
    async def _check_rule(self, rule_name: str, rule_config: Dict[str, Any], current_time: float):
        """Check specific alert rule."""
        if rule_name == "no_frames_5m":
            await self._check_no_frames(rule_config, current_time)
        elif rule_name == "decode_error_rate":
            await self._check_decode_error_rate(rule_config, current_time)
        elif rule_name == "queue_length":
            await self._check_queue_length(rule_config, current_time)
        elif rule_name == "database_errors":
            await self._check_database_errors(rule_config, current_time)
        elif rule_name == "high_latency":
            await self._check_high_latency(rule_config, current_time)
    
    async def _check_no_frames(self, rule_config: Dict[str, Any], current_time: float):
        """Check for no frames received."""
        from app.metrics import get_metrics
        
        metrics = get_metrics()
        frames_received = metrics.get("counters", {}).get("frames_received_total", 0)
        
        if frames_received == 0:
            # Check if we've been without frames for the threshold time
            time_since_last_frame = current_time - self.last_check
            if time_since_last_frame >= rule_config["threshold"]:
                self._trigger_alert(
                    "no_frames_5m",
                    rule_config["severity"],
                    rule_config["message"].format(threshold=rule_config["threshold"]),
                    current_time,
                    {"metric": "frames_received_total"},
                    time_since_last_frame,
                    rule_config["threshold"]
                )
    
    async def _check_decode_error_rate(self, rule_config: Dict[str, Any], current_time: float):
        """Check decode error rate."""
        from app.metrics import get_metrics
        
        metrics = get_metrics()
        total_frames = metrics.get("counters", {}).get("frames_received_total", 0)
        decode_errors = metrics.get("counters", {}).get("can_decode_errors_total", 0)
        
        if total_frames > 0:
            error_rate = (decode_errors / total_frames) * 100
            if error_rate >= rule_config["threshold"]:
                self._trigger_alert(
                    "decode_error_rate",
                    rule_config["severity"],
                    rule_config["message"].format(value=error_rate, threshold=rule_config["threshold"]),
                    current_time,
                    {"metric": "decode_error_rate"},
                    error_rate,
                    rule_config["threshold"]
                )
    
    async def _check_queue_length(self, rule_config: Dict[str, Any], current_time: float):
        """Check queue length."""
        from app.backpressure import backpressure_manager
        
        stats = backpressure_manager.get_all_stats()
        total_queue_size = sum(stat.size for stat in stats.values())
        
        if total_queue_size >= rule_config["threshold"]:
            self._trigger_alert(
                "queue_length",
                rule_config["severity"],
                rule_config["message"].format(value=total_queue_size, threshold=rule_config["threshold"]),
                current_time,
                {"metric": "queue_length"},
                total_queue_size,
                rule_config["threshold"]
            )
    
    async def _check_database_errors(self, rule_config: Dict[str, Any], current_time: float):
        """Check database errors."""
        from app.metrics import get_metrics
        
        metrics = get_metrics()
        db_errors = metrics.get("counters", {}).get("database_operations_total{success=false}", 0)
        
        if db_errors >= rule_config["threshold"]:
            self._trigger_alert(
                "database_errors",
                rule_config["severity"],
                rule_config["message"].format(value=db_errors, threshold=rule_config["threshold"]),
                current_time,
                {"metric": "database_errors"},
                db_errors,
                rule_config["threshold"]
            )
    
    async def _check_high_latency(self, rule_config: Dict[str, Any], current_time: float):
        """Check for high latency."""
        from app.metrics import get_metrics
        
        metrics = get_metrics()
        timers = metrics.get("timers", {})
        
        for timer_name, timer_stats in timers.items():
            if "latency" in timer_name.lower():
                avg_latency = timer_stats.get("avg", 0) * 1000  # Convert to ms
                if avg_latency >= rule_config["threshold"]:
                    self._trigger_alert(
                        "high_latency",
                        rule_config["severity"],
                        rule_config["message"].format(value=avg_latency, threshold=rule_config["threshold"]),
                        current_time,
                        {"metric": timer_name},
                        avg_latency,
                        rule_config["threshold"]
                    )
    
    def _trigger_alert(self, name: str, severity: AlertSeverity, message: str, 
                      timestamp: float, labels: Dict[str, str], value: float, threshold: float):
        """Trigger an alert."""
        alert = Alert(
            name=name,
            severity=severity,
            message=message,
            timestamp=timestamp,
            labels=labels,
            value=value,
            threshold=threshold
        )
        
        self.alerts[name] = alert
        
        # Log alert
        logger.warning(
            "alert_triggered",
            name=name,
            severity=severity.value,
            message=message,
            value=value,
            threshold=threshold,
            labels=labels
        )
        
        # TODO: Send to external alerting system (PagerDuty, Slack, etc.)
    
    def resolve_alert(self, name: str):
        """Resolve an alert."""
        if name in self.alerts:
            del self.alerts[name]
            logger.info("alert_resolved", name=name)
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return list(self.alerts.values())
    
    def update_rule(self, rule_name: str, rule_config: Dict[str, Any]):
        """Update alert rule configuration."""
        if rule_name in self.rules:
            self.rules[rule_name].update(rule_config)
            logger.info("alert_rule_updated", rule=rule_name, config=rule_config)


# Global alert manager
alert_manager = AlertManager()
