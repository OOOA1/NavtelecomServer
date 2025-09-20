"""
SLO (Service Level Objectives) and burn-rate alerting system.
"""
import time
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

@dataclass
class SLOTarget:
    """SLO target definition."""
    name: str
    metric: str
    target_p99: float  # milliseconds
    target_p95: float  # milliseconds
    target_p50: float  # milliseconds
    burn_rate_1h: float = 0.02  # 2% error rate over 1 hour
    burn_rate_6h: float = 0.05  # 5% error rate over 6 hours
    window_size: int = 300  # 5 minutes window

@dataclass
class LatencyMeasurement:
    """Single latency measurement."""
    timestamp: float
    value: float  # milliseconds
    success: bool
    device_id: Optional[str] = None
    operation: Optional[str] = None

class SLOManager:
    """SLO monitoring and burn-rate alerting."""
    
    def __init__(self):
        self.slo_targets = {
            "ack_latency": SLOTarget(
                name="ACK Latency",
                metric="ack_latency_ms",
                target_p99=200.0,
                target_p95=100.0,
                target_p50=50.0
            ),
            "decode_latency": SLOTarget(
                name="Decode Latency", 
                metric="decode_latency_ms",
                target_p99=500.0,
                target_p95=250.0,
                target_p50=100.0
            ),
            "api_latency": SLOTarget(
                name="API Latency",
                metric="api_latency_ms", 
                target_p99=300.0,
                target_p95=150.0,
                target_p50=75.0
            ),
            "db_insert_latency": SLOTarget(
                name="DB Insert Latency",
                metric="db_insert_latency_ms",
                target_p99=1000.0,
                target_p95=500.0,
                target_p50=200.0
            )
        }
        
        # Rolling windows for each SLO
        self.measurements: Dict[str, List[LatencyMeasurement]] = {
            target: [] for target in self.slo_targets.keys()
        }
        
        # Burn rate tracking
        self.burn_rate_alerts: Dict[str, bool] = {
            target: False for target in self.slo_targets.keys()
        }
        
        # Start background monitoring
        self._monitoring_task = None
        
    async def start_monitoring(self):
        """Start background SLO monitoring."""
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitor_loop())
            logger.info("slo_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop background SLO monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
            logger.info("slo_monitoring_stopped")
    
    def record_measurement(self, target_name: str, latency_ms: float, 
                          success: bool, device_id: Optional[str] = None,
                          operation: Optional[str] = None):
        """Record a latency measurement."""
        if target_name not in self.slo_targets:
            logger.warning("unknown_slo_target", target=target_name)
            return
            
        measurement = LatencyMeasurement(
            timestamp=time.time(),
            value=latency_ms,
            success=success,
            device_id=device_id,
            operation=operation
        )
        
        self.measurements[target_name].append(measurement)
        
        # Keep only recent measurements (last 2 hours)
        cutoff_time = time.time() - 7200
        self.measurements[target_name] = [
            m for m in self.measurements[target_name] 
            if m.timestamp > cutoff_time
        ]
    
    def get_current_slo_status(self, target_name: str) -> Dict:
        """Get current SLO status for a target."""
        if target_name not in self.slo_targets:
            return {"error": "Unknown target"}
            
        target = self.slo_targets[target_name]
        measurements = self.measurements[target_name]
        
        if not measurements:
            return {
                "target": target_name,
                "status": "no_data",
                "measurements_count": 0
            }
        
        # Calculate percentiles
        recent_measurements = [
            m for m in measurements 
            if m.timestamp > time.time() - target.window_size
        ]
        
        if not recent_measurements:
            return {
                "target": target_name,
                "status": "no_recent_data",
                "measurements_count": len(measurements)
            }
        
        # Sort by latency
        latencies = sorted([m.value for m in recent_measurements])
        total = len(latencies)
        
        p50 = latencies[int(total * 0.5)] if total > 0 else 0
        p95 = latencies[int(total * 0.95)] if total > 0 else 0
        p99 = latencies[int(total * 0.99)] if total > 0 else 0
        
        # Calculate success rate
        successful = sum(1 for m in recent_measurements if m.success)
        success_rate = successful / total if total > 0 else 0
        
        # Check SLO compliance
        p99_ok = p99 <= target.target_p99
        p95_ok = p95 <= target.target_p95
        p50_ok = p50 <= target.target_p50
        
        status = "healthy" if (p99_ok and p95_ok and p50_ok) else "degraded"
        
        return {
            "target": target_name,
            "status": status,
            "measurements_count": len(recent_measurements),
            "percentiles": {
                "p50": p50,
                "p95": p95,
                "p99": p99
            },
            "targets": {
                "p50": target.target_p50,
                "p95": target.target_p95,
                "p99": target.target_p99
            },
            "success_rate": success_rate,
            "compliance": {
                "p50_ok": p50_ok,
                "p95_ok": p95_ok,
                "p99_ok": p99_ok
            }
        }
    
    def check_burn_rate(self, target_name: str) -> Dict:
        """Check burn rate for a target."""
        if target_name not in self.slo_targets:
            return {"error": "Unknown target"}
            
        target = self.slo_targets[target_name]
        measurements = self.measurements[target_name]
        
        if not measurements:
            return {
                "target": target_name,
                "burn_rate_1h": 0.0,
                "burn_rate_6h": 0.0,
                "alert_1h": False,
                "alert_6h": False
            }
        
        now = time.time()
        
        # Calculate 1-hour burn rate
        measurements_1h = [
            m for m in measurements 
            if m.timestamp > now - 3600
        ]
        
        # Calculate 6-hour burn rate  
        measurements_6h = [
            m for m in measurements
            if m.timestamp > now - 21600
        ]
        
        def calculate_burn_rate(measurements_list: List[LatencyMeasurement]) -> float:
            if not measurements_list:
                return 0.0
            
            # Count errors (failed measurements or exceeded SLO)
            errors = 0
            for m in measurements_list:
                if not m.success or m.value > target.target_p99:
                    errors += 1
            
            return errors / len(measurements_list)
        
        burn_rate_1h = calculate_burn_rate(measurements_1h)
        burn_rate_6h = calculate_burn_rate(measurements_6h)
        
        alert_1h = burn_rate_1h > target.burn_rate_1h
        alert_6h = burn_rate_6h > target.burn_rate_6h
        
        return {
            "target": target_name,
            "burn_rate_1h": burn_rate_1h,
            "burn_rate_6h": burn_rate_6h,
            "threshold_1h": target.burn_rate_1h,
            "threshold_6h": target.burn_rate_6h,
            "alert_1h": alert_1h,
            "alert_6h": alert_6h,
            "measurements_1h": len(measurements_1h),
            "measurements_6h": len(measurements_6h)
        }
    
    async def _monitor_loop(self):
        """Background monitoring loop."""
        while True:
            try:
                await self._check_all_slos()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("slo_monitoring_error", error=str(e))
                await asyncio.sleep(60)
    
    async def _check_all_slos(self):
        """Check all SLOs and trigger alerts."""
        for target_name in self.slo_targets.keys():
            # Check burn rate
            burn_rate_status = self.check_burn_rate(target_name)
            
            # Check if we need to trigger/clear alerts
            alert_1h = burn_rate_status.get("alert_1h", False)
            alert_6h = burn_rate_status.get("alert_6h", False)
            
            if alert_1h or alert_6h:
                if not self.burn_rate_alerts[target_name]:
                    # New alert
                    self.burn_rate_alerts[target_name] = True
                    await self._trigger_burn_rate_alert(target_name, burn_rate_status)
            else:
                if self.burn_rate_alerts[target_name]:
                    # Clear alert
                    self.burn_rate_alerts[target_name] = False
                    await self._clear_burn_rate_alert(target_name)
    
    async def _trigger_burn_rate_alert(self, target_name: str, burn_rate_status: Dict):
        """Trigger burn rate alert."""
        logger.error(
            "burn_rate_alert_triggered",
            target=target_name,
            burn_rate_1h=burn_rate_status.get("burn_rate_1h", 0),
            burn_rate_6h=burn_rate_status.get("burn_rate_6h", 0),
            threshold_1h=burn_rate_status.get("threshold_1h", 0),
            threshold_6h=burn_rate_status.get("threshold_6h", 0)
        )
        
        # Here you would integrate with your alerting system
        # (PagerDuty, Slack, email, etc.)
    
    async def _clear_burn_rate_alert(self, target_name: str):
        """Clear burn rate alert."""
        logger.info("burn_rate_alert_cleared", target=target_name)
        
        # Here you would clear the alert in your alerting system

# Global SLO manager instance
slo_manager = SLOManager()
