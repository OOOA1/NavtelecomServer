"""
Backup monitoring and alerting system.
"""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import structlog
import subprocess
import json

logger = structlog.get_logger()


class BackupMonitor:
    """Monitors backup status and sends alerts."""
    
    def __init__(self):
        self.last_full_backup_time: Optional[datetime] = None
        self.last_wal_backup_time: Optional[datetime] = None
        self.backup_status: Dict[str, Any] = {}
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.full_backup_max_age_hours = 26  # Alert if no full backup for 26 hours
        self.wal_backup_max_age_minutes = 10  # Alert if no WAL backup for 10 minutes
        self.backup_retention_days = 30
        
        logger.info("backup_monitor_initialized")
    
    async def check_backup_status(self) -> Dict[str, Any]:
        """Check current backup status."""
        status = {
            "full_backup": await self._check_full_backup(),
            "wal_backup": await self._check_wal_backup(),
            "backup_integrity": await self._check_backup_integrity(),
            "retention_policy": await self._check_retention_policy(),
            "storage_usage": await self._check_storage_usage()
        }
        
        self.backup_status = status
        return status
    
    async def _check_full_backup(self) -> Dict[str, Any]:
        """Check full backup status."""
        try:
            # Check if wal-g is available
            result = subprocess.run(
                ["wal-g", "backup-list"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"wal-g backup-list failed: {result.stderr}",
                    "last_backup": None,
                    "age_hours": None
                }
            
            # Parse backup list
            lines = result.stdout.strip().split('\n')
            if len(lines) < 2:  # Header + at least one backup
                return {
                    "status": "error",
                    "message": "No backups found",
                    "last_backup": None,
                    "age_hours": None
                }
            
            # Get latest backup (second line, first column)
            latest_backup_line = lines[1]
            backup_parts = latest_backup_line.split()
            if len(backup_parts) < 3:
                return {
                    "status": "error",
                    "message": "Invalid backup list format",
                    "last_backup": None,
                    "age_hours": None
                }
            
            backup_name = backup_parts[0]
            backup_time_str = f"{backup_parts[1]} {backup_parts[2]}"
            
            # Parse backup time
            try:
                backup_time = datetime.strptime(backup_time_str, "%Y-%m-%d %H:%M:%S")
                backup_time = backup_time.replace(tzinfo=timezone.utc)
                
                age_hours = (datetime.now(timezone.utc) - backup_time).total_seconds() / 3600
                
                status = "ok"
                if age_hours > self.full_backup_max_age_hours:
                    status = "warning"
                
                return {
                    "status": status,
                    "message": f"Last backup: {backup_name}",
                    "last_backup": backup_name,
                    "age_hours": round(age_hours, 2)
                }
                
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse backup time: {e}",
                    "last_backup": None,
                    "age_hours": None
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "wal-g command timed out",
                "last_backup": None,
                "age_hours": None
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Unexpected error: {e}",
                "last_backup": None,
                "age_hours": None
            }
    
    async def _check_wal_backup(self) -> Dict[str, Any]:
        """Check WAL backup status."""
        try:
            # Check WAL archiving status
            result = subprocess.run(
                ["psql", "-t", "-c", "SELECT archived_count, last_archived_time FROM pg_stat_archiver;"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Failed to check WAL archiving: {result.stderr}",
                    "last_archived": None,
                    "age_minutes": None
                }
            
            # Parse result
            lines = result.stdout.strip().split('\n')
            if not lines or not lines[0].strip():
                return {
                    "status": "error",
                    "message": "No WAL archiving data found",
                    "last_archived": None,
                    "age_minutes": None
                }
            
            parts = lines[0].strip().split('|')
            if len(parts) < 2:
                return {
                    "status": "error",
                    "message": "Invalid WAL archiving data format",
                    "last_archived": None,
                    "age_minutes": None
                }
            
            archived_count = parts[0].strip()
            last_archived_time_str = parts[1].strip()
            
            if last_archived_time_str == "" or last_archived_time_str == "NULL":
                return {
                    "status": "warning",
                    "message": "No WAL files archived yet",
                    "last_archived": None,
                    "age_minutes": None
                }
            
            # Parse last archived time
            try:
                last_archived_time = datetime.fromisoformat(last_archived_time_str.replace(' ', 'T'))
                if last_archived_time.tzinfo is None:
                    last_archived_time = last_archived_time.replace(tzinfo=timezone.utc)
                
                age_minutes = (datetime.now(timezone.utc) - last_archived_time).total_seconds() / 60
                
                status = "ok"
                if age_minutes > self.wal_backup_max_age_minutes:
                    status = "warning"
                
                return {
                    "status": status,
                    "message": f"Archived {archived_count} WAL files",
                    "last_archived": last_archived_time_str,
                    "age_minutes": round(age_minutes, 2)
                }
                
            except ValueError as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse last archived time: {e}",
                    "last_archived": None,
                    "age_minutes": None
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "WAL check command timed out",
                "last_archived": None,
                "age_minutes": None
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Unexpected error: {e}",
                "last_archived": None,
                "age_minutes": None
            }
    
    async def _check_backup_integrity(self) -> Dict[str, Any]:
        """Check backup integrity."""
        try:
            # Try to list backups to verify connectivity
            result = subprocess.run(
                ["wal-g", "backup-list"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Backup integrity check failed: {result.stderr}",
                    "accessible_backups": 0
                }
            
            # Count accessible backups
            lines = result.stdout.strip().split('\n')
            accessible_backups = max(0, len(lines) - 1)  # Subtract header line
            
            status = "ok"
            if accessible_backups == 0:
                status = "warning"
                message = "No accessible backups found"
            else:
                message = f"Found {accessible_backups} accessible backups"
            
            return {
                "status": status,
                "message": message,
                "accessible_backups": accessible_backups
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Backup integrity check failed: {e}",
                "accessible_backups": 0
            }
    
    async def _check_retention_policy(self) -> Dict[str, Any]:
        """Check backup retention policy."""
        try:
            # Check if retention policy is being enforced
            result = subprocess.run(
                ["wal-g", "backup-list"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Failed to check retention policy: {result.stderr}",
                    "total_backups": 0,
                    "oldest_backup": None
                }
            
            lines = result.stdout.strip().split('\n')
            if len(lines) < 2:
                return {
                    "status": "warning",
                    "message": "No backups found for retention check",
                    "total_backups": 0,
                    "oldest_backup": None
                }
            
            total_backups = len(lines) - 1  # Subtract header
            oldest_backup_line = lines[-1]  # Last line is oldest
            oldest_backup_parts = oldest_backup_line.split()
            
            if len(oldest_backup_parts) >= 3:
                oldest_backup_time_str = f"{oldest_backup_parts[1]} {oldest_backup_parts[2]}"
                try:
                    oldest_backup_time = datetime.strptime(oldest_backup_time_str, "%Y-%m-%d %H:%M:%S")
                    oldest_backup_time = oldest_backup_time.replace(tzinfo=timezone.utc)
                    
                    age_days = (datetime.now(timezone.utc) - oldest_backup_time).days
                    
                    status = "ok"
                    if age_days > self.backup_retention_days:
                        status = "warning"
                        message = f"Oldest backup is {age_days} days old (retention: {self.backup_retention_days} days)"
                    else:
                        message = f"Retention policy OK (oldest backup: {age_days} days)"
                    
                    return {
                        "status": status,
                        "message": message,
                        "total_backups": total_backups,
                        "oldest_backup": oldest_backup_time_str,
                        "age_days": age_days
                    }
                    
                except ValueError:
                    pass
            
            return {
                "status": "ok",
                "message": f"Found {total_backups} backups",
                "total_backups": total_backups,
                "oldest_backup": None
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Retention policy check failed: {e}",
                "total_backups": 0,
                "oldest_backup": None
            }
    
    async def _check_storage_usage(self) -> Dict[str, Any]:
        """Check storage usage."""
        try:
            # Check local disk usage
            result = subprocess.run(
                ["df", "-h", "/var/lib/postgresql"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Failed to check disk usage: {result.stderr}",
                    "usage_percent": None
                }
            
            lines = result.stdout.strip().split('\n')
            if len(lines) < 2:
                return {
                    "status": "error",
                    "message": "Invalid disk usage output",
                    "usage_percent": None
                }
            
            # Parse usage percentage
            parts = lines[1].split()
            if len(parts) >= 5:
                usage_str = parts[4].replace('%', '')
                try:
                    usage_percent = float(usage_str)
                    
                    status = "ok"
                    if usage_percent > 90:
                        status = "critical"
                    elif usage_percent > 80:
                        status = "warning"
                    
                    return {
                        "status": status,
                        "message": f"Disk usage: {usage_percent}%",
                        "usage_percent": usage_percent
                    }
                    
                except ValueError:
                    pass
            
            return {
                "status": "ok",
                "message": "Disk usage check completed",
                "usage_percent": None
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Storage usage check failed: {e}",
                "usage_percent": None
            }
    
    async def send_alerts(self, status: Dict[str, Any]):
        """Send alerts based on backup status."""
        alerts = []
        
        # Check full backup
        if status["full_backup"]["status"] in ["warning", "error"]:
            alerts.append({
                "severity": "warning" if status["full_backup"]["status"] == "warning" else "critical",
                "message": f"Full backup issue: {status['full_backup']['message']}",
                "component": "backup_full"
            })
        
        # Check WAL backup
        if status["wal_backup"]["status"] in ["warning", "error"]:
            alerts.append({
                "severity": "warning" if status["wal_backup"]["status"] == "warning" else "critical",
                "message": f"WAL backup issue: {status['wal_backup']['message']}",
                "component": "backup_wal"
            })
        
        # Check backup integrity
        if status["backup_integrity"]["status"] in ["warning", "error"]:
            alerts.append({
                "severity": "critical",
                "message": f"Backup integrity issue: {status['backup_integrity']['message']}",
                "component": "backup_integrity"
            })
        
        # Check storage usage
        if status["storage_usage"]["status"] in ["warning", "critical"]:
            alerts.append({
                "severity": status["storage_usage"]["status"],
                "message": f"Storage issue: {status['storage_usage']['message']}",
                "component": "storage"
            })
        
        # Send alerts
        for alert in alerts:
            await self._send_alert(alert)
    
    async def _send_alert(self, alert: Dict[str, Any]):
        """Send individual alert."""
        logger.error(
            "backup_alert",
            severity=alert["severity"],
            component=alert["component"],
            message=alert["message"]
        )
        
        # Send to alert manager
        from app.alerts import alert_manager, AlertSeverity
        
        severity_map = {
            "warning": AlertSeverity.WARNING,
            "critical": AlertSeverity.CRITICAL
        }
        
        alert_manager.raise_alert(
            name=f"Backup_{alert['component']}",
            severity=severity_map.get(alert["severity"], AlertSeverity.WARNING),
            message=alert["message"],
            labels={"component": alert["component"]},
            value=1,
            threshold=1
        )
    
    async def _monitor_backups(self):
        """Background monitoring task."""
        while True:
            try:
                status = await self.check_backup_status()
                await self.send_alerts(status)
                
                logger.info("backup_monitoring_check", status=status)
                
            except Exception as e:
                logger.error("backup_monitoring_error", error=str(e))
            
            # Check every 5 minutes
            await asyncio.sleep(300)
    
    async def start_monitoring(self):
        """Start backup monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_backups())
            logger.info("backup_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop backup monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("backup_monitoring_stopped")
            self.monitoring_task = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current backup status."""
        return self.backup_status


backup_monitor = BackupMonitor()

