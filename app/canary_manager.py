"""
Canary deployment manager for API versioning.
"""
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from app.feature_flags import feature_flags

logger = structlog.get_logger()


class CanaryManager:
    """Manages canary deployments and traffic routing."""
    
    def __init__(self):
        self.canary_configs: Dict[str, Dict[str, Any]] = {}
        self.canary_metrics: Dict[str, Dict[str, Any]] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Default canary configuration
        self.default_config = {
            "enabled": False,
            "percentage": 5,
            "duration_minutes": 30,
            "success_threshold": 0.95,
            "error_threshold": 0.05,
            "latency_threshold_ms": 1000
        }
        
        logger.info("canary_manager_initialized")
    
    def configure_canary(self, feature: str, config: Dict[str, Any]):
        """Configure canary deployment for a feature."""
        self.canary_configs[feature] = {**self.default_config, **config}
        logger.info("canary_configured", feature=feature, config=config)
    
    def is_canary_enabled(self, feature: str) -> bool:
        """Check if canary is enabled for a feature."""
        config = self.canary_configs.get(feature, self.default_config)
        return config["enabled"] and feature_flags.is_canary_enabled(feature)
    
    def should_use_canary(self, feature: str, identifier: str) -> bool:
        """Check if identifier should use canary version."""
        if not self.is_canary_enabled(feature):
            return False
        
        config = self.canary_configs.get(feature, self.default_config)
        percentage = config["percentage"]
        
        # Hash-based canary selection
        hash_value = int(hashlib.md5(identifier.encode()).hexdigest(), 16)
        return (hash_value % 100) < percentage
    
    def get_canary_percentage(self, feature: str) -> int:
        """Get canary percentage for a feature."""
        config = self.canary_configs.get(feature, self.default_config)
        return config["percentage"]
    
    def set_canary_percentage(self, feature: str, percentage: int):
        """Set canary percentage for a feature."""
        if feature not in self.canary_configs:
            self.canary_configs[feature] = self.default_config.copy()
        
        self.canary_configs[feature]["percentage"] = max(0, min(100, percentage))
        logger.info("canary_percentage_updated", feature=feature, percentage=percentage)
    
    def enable_canary(self, feature: str):
        """Enable canary deployment for a feature."""
        if feature not in self.canary_configs:
            self.canary_configs[feature] = self.default_config.copy()
        
        self.canary_configs[feature]["enabled"] = True
        self.canary_configs[feature]["started_at"] = datetime.now(timezone.utc)
        
        logger.info("canary_enabled", feature=feature)
    
    def disable_canary(self, feature: str):
        """Disable canary deployment for a feature."""
        if feature in self.canary_configs:
            self.canary_configs[feature]["enabled"] = False
            self.canary_configs[feature]["stopped_at"] = datetime.now(timezone.utc)
            
            logger.info("canary_disabled", feature=feature)
    
    def record_canary_metric(self, feature: str, metric_type: str, value: float, 
                           labels: Optional[Dict[str, str]] = None):
        """Record canary metric."""
        if feature not in self.canary_metrics:
            self.canary_metrics[feature] = {
                "requests": 0,
                "errors": 0,
                "latency_sum": 0.0,
                "latency_count": 0,
                "start_time": datetime.now(timezone.utc)
            }
        
        metrics = self.canary_metrics[feature]
        
        if metric_type == "request":
            metrics["requests"] += 1
        elif metric_type == "error":
            metrics["errors"] += 1
        elif metric_type == "latency":
            metrics["latency_sum"] += value
            metrics["latency_count"] += 1
        
        # Add custom labels
        if labels:
            if "labels" not in metrics:
                metrics["labels"] = {}
            metrics["labels"].update(labels)
        
        logger.debug("canary_metric_recorded", 
                    feature=feature, 
                    metric_type=metric_type, 
                    value=value)
    
    def get_canary_metrics(self, feature: str) -> Dict[str, Any]:
        """Get canary metrics for a feature."""
        if feature not in self.canary_metrics:
            return {}
        
        metrics = self.canary_metrics[feature]
        
        # Calculate derived metrics
        total_requests = metrics["requests"]
        total_errors = metrics["errors"]
        
        error_rate = (total_errors / total_requests) if total_requests > 0 else 0
        success_rate = 1 - error_rate
        
        avg_latency = (metrics["latency_sum"] / metrics["latency_count"]) if metrics["latency_count"] > 0 else 0
        
        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": error_rate,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency,
            "start_time": metrics["start_time"],
            "labels": metrics.get("labels", {})
        }
    
    def check_canary_health(self, feature: str) -> Dict[str, Any]:
        """Check canary health and determine if it should continue."""
        if not self.is_canary_enabled(feature):
            return {"healthy": True, "reason": "canary_disabled"}
        
        config = self.canary_configs.get(feature, self.default_config)
        metrics = self.get_canary_metrics(feature)
        
        if not metrics:
            return {"healthy": True, "reason": "no_metrics"}
        
        # Check error threshold
        if metrics["error_rate"] > config["error_threshold"]:
            return {
                "healthy": False, 
                "reason": "error_threshold_exceeded",
                "error_rate": metrics["error_rate"],
                "threshold": config["error_threshold"]
            }
        
        # Check success threshold
        if metrics["success_rate"] < config["success_threshold"]:
            return {
                "healthy": False,
                "reason": "success_threshold_not_met",
                "success_rate": metrics["success_rate"],
                "threshold": config["success_threshold"]
            }
        
        # Check latency threshold
        if metrics["avg_latency_ms"] > config["latency_threshold_ms"]:
            return {
                "healthy": False,
                "reason": "latency_threshold_exceeded",
                "avg_latency_ms": metrics["avg_latency_ms"],
                "threshold": config["latency_threshold_ms"]
            }
        
        return {"healthy": True, "reason": "all_checks_passed"}
    
    def should_rollback_canary(self, feature: str) -> bool:
        """Check if canary should be rolled back."""
        health = self.check_canary_health(feature)
        return not health["healthy"]
    
    def get_canary_status(self, feature: str) -> Dict[str, Any]:
        """Get comprehensive canary status."""
        config = self.canary_configs.get(feature, self.default_config)
        metrics = self.get_canary_metrics(feature)
        health = self.check_canary_health(feature)
        
        return {
            "feature": feature,
            "enabled": config["enabled"],
            "percentage": config["percentage"],
            "health": health,
            "metrics": metrics,
            "config": config
        }
    
    async def _monitor_canary_health(self):
        """Background task to monitor canary health."""
        while True:
            try:
                for feature in list(self.canary_configs.keys()):
                    if self.is_canary_enabled(feature):
                        health = self.check_canary_health(feature)
                        
                        if not health["healthy"]:
                            logger.warning("canary_unhealthy", 
                                         feature=feature, 
                                         health=health)
                            
                            # Auto-disable if unhealthy
                            self.disable_canary(feature)
                            
                            # Send alert
                            from app.alerts import alert_manager, AlertSeverity
                            alert_manager.raise_alert(
                                name=f"CanaryUnhealthy_{feature}",
                                severity=AlertSeverity.CRITICAL,
                                message=f"Canary deployment for {feature} is unhealthy: {health['reason']}",
                                labels={"feature": feature, "reason": health["reason"]},
                                value=1,
                                threshold=1
                            )
                
                # Clean up old metrics
                self._cleanup_old_metrics()
                
            except Exception as e:
                logger.error("canary_monitoring_error", error=str(e))
            
            # Check every minute
            await asyncio.sleep(60)
    
    def _cleanup_old_metrics(self):
        """Clean up old canary metrics."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - 3600  # 1 hour ago
        
        for feature in list(self.canary_metrics.keys()):
            metrics = self.canary_metrics[feature]
            if metrics["start_time"].timestamp() < cutoff_time:
                del self.canary_metrics[feature]
                logger.debug("canary_metrics_cleaned", feature=feature)
    
    async def start_monitoring(self):
        """Start canary monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_canary_health())
            logger.info("canary_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop canary monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("canary_monitoring_stopped")
            self.monitoring_task = None


# Global canary manager
canary_manager = CanaryManager()

