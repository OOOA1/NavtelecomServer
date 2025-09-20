"""
Security monitoring and threat detection system.
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import structlog
import ipaddress
import re

logger = structlog.get_logger()


class SecurityMonitor:
    """Monitors security events and detects threats."""
    
    def __init__(self):
        self.connection_attempts: Dict[str, List[datetime]] = {}
        self.failed_auth_attempts: Dict[str, List[datetime]] = {}
        self.suspicious_ips: set = set()
        self.blocked_ips: set = set()
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.max_connections_per_minute = 10
        self.max_failed_auth_per_minute = 5
        self.block_duration_minutes = 60
        self.cleanup_interval_minutes = 5
        
        # IP allowlist
        self.allowed_networks = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
        ]
        
        # Suspicious patterns
        self.suspicious_patterns = [
            r"admin",
            r"root",
            r"test",
            r"guest",
            r"user",
            r"password",
            r"login",
            r"sql",
            r"script",
            r"eval",
            r"exec",
            r"system",
            r"cmd",
            r"shell",
        ]
        
        logger.info("security_monitor_initialized")
    
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is in allowlist."""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return any(ip_obj in network for network in self.allowed_networks)
        except ValueError:
            return False
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked."""
        return ip in self.blocked_ips
    
    def record_connection_attempt(self, ip: str, success: bool = True):
        """Record a connection attempt."""
        now = datetime.now(timezone.utc)
        
        if ip not in self.connection_attempts:
            self.connection_attempts[ip] = []
        
        self.connection_attempts[ip].append(now)
        
        # Clean old attempts
        cutoff = now - timedelta(minutes=1)
        self.connection_attempts[ip] = [
            attempt for attempt in self.connection_attempts[ip] if attempt > cutoff
        ]
        
        # Check for suspicious activity
        if len(self.connection_attempts[ip]) > self.max_connections_per_minute:
            self._handle_suspicious_activity(ip, "high_connection_rate", {
                "attempts": len(self.connection_attempts[ip]),
                "threshold": self.max_connections_per_minute
            })
        
        logger.debug("connection_attempt_recorded", ip=ip, success=success)
    
    def record_failed_auth(self, ip: str, username: str = "", endpoint: str = ""):
        """Record a failed authentication attempt."""
        now = datetime.now(timezone.utc)
        
        if ip not in self.failed_auth_attempts:
            self.failed_auth_attempts[ip] = []
        
        self.failed_auth_attempts[ip].append(now)
        
        # Clean old attempts
        cutoff = now - timedelta(minutes=1)
        self.failed_auth_attempts[ip] = [
            attempt for attempt in self.failed_auth_attempts[ip] if attempt > cutoff
        ]
        
        # Check for brute force
        if len(self.failed_auth_attempts[ip]) > self.max_failed_auth_per_minute:
            self._handle_suspicious_activity(ip, "brute_force", {
                "attempts": len(self.failed_auth_attempts[ip]),
                "threshold": self.max_failed_auth_per_minute,
                "username": username,
                "endpoint": endpoint
            })
        
        # Check for suspicious usernames
        if self._is_suspicious_username(username):
            self._handle_suspicious_activity(ip, "suspicious_username", {
                "username": username,
                "endpoint": endpoint
            })
        
        logger.warning("failed_auth_recorded", ip=ip, username=username, endpoint=endpoint)
    
    def _is_suspicious_username(self, username: str) -> bool:
        """Check if username contains suspicious patterns."""
        if not username:
            return False
        
        username_lower = username.lower()
        return any(pattern in username_lower for pattern in self.suspicious_patterns)
    
    def _handle_suspicious_activity(self, ip: str, activity_type: str, details: Dict[str, Any]):
        """Handle suspicious activity."""
        if ip in self.blocked_ips:
            return  # Already blocked
        
        self.suspicious_ips.add(ip)
        
        # Block IP if not in allowlist
        if not self.is_ip_allowed(ip):
            self.blocked_ips.add(ip)
            
            # Schedule unblock
            asyncio.create_task(self._schedule_unblock(ip))
            
            logger.error(
                "ip_blocked",
                ip=ip,
                activity_type=activity_type,
                details=details
            )
            
            # Send alert
            self._send_security_alert(ip, activity_type, details)
        else:
            logger.warning(
                "suspicious_activity_allowed_ip",
                ip=ip,
                activity_type=activity_type,
                details=details
            )
    
    async def _schedule_unblock(self, ip: str):
        """Schedule IP unblock after block duration."""
        await asyncio.sleep(self.block_duration_minutes * 60)
        
        if ip in self.blocked_ips:
            self.blocked_ips.remove(ip)
            logger.info("ip_unblocked", ip=ip)
    
    def _send_security_alert(self, ip: str, activity_type: str, details: Dict[str, Any]):
        """Send security alert."""
        from app.alerts import alert_manager, AlertSeverity
        
        alert_manager.raise_alert(
            name=f"Security_{activity_type}",
            severity=AlertSeverity.CRITICAL,
            message=f"Suspicious activity detected from {ip}: {activity_type}",
            labels={
                "ip": ip,
                "activity_type": activity_type,
                "details": str(details)
            },
            value=1,
            threshold=1
        )
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current security status."""
        now = datetime.now(timezone.utc)
        
        # Count recent connection attempts
        recent_connections = 0
        for ip, attempts in self.connection_attempts.items():
            cutoff = now - timedelta(minutes=1)
            recent_connections += len([a for a in attempts if a > cutoff])
        
        # Count recent failed auth attempts
        recent_failed_auth = 0
        for ip, attempts in self.failed_auth_attempts.items():
            cutoff = now - timedelta(minutes=1)
            recent_failed_auth += len([a for a in attempts if a > cutoff])
        
        return {
            "blocked_ips": len(self.blocked_ips),
            "suspicious_ips": len(self.suspicious_ips),
            "recent_connections": recent_connections,
            "recent_failed_auth": recent_failed_auth,
            "blocked_ips_list": list(self.blocked_ips),
            "suspicious_ips_list": list(self.suspicious_ips)
        }
    
    async def _cleanup_old_data(self):
        """Clean up old monitoring data."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=1)
        
        # Clean connection attempts
        for ip in list(self.connection_attempts.keys()):
            self.connection_attempts[ip] = [
                attempt for attempt in self.connection_attempts[ip] if attempt > cutoff
            ]
            if not self.connection_attempts[ip]:
                del self.connection_attempts[ip]
        
        # Clean failed auth attempts
        for ip in list(self.failed_auth_attempts.keys()):
            self.failed_auth_attempts[ip] = [
                attempt for attempt in self.failed_auth_attempts[ip] if attempt > cutoff
            ]
            if not self.failed_auth_attempts[ip]:
                del self.failed_auth_attempts[ip]
        
        logger.debug("security_data_cleaned")
    
    async def _monitor_security(self):
        """Background security monitoring task."""
        while True:
            try:
                await self._cleanup_old_data()
                
                # Check for persistent suspicious activity
                for ip in list(self.suspicious_ips):
                    if ip not in self.blocked_ips and not self.is_ip_allowed(ip):
                        # Check if IP is still active
                        recent_connections = 0
                        if ip in self.connection_attempts:
                            now = datetime.now(timezone.utc)
                            cutoff = now - timedelta(minutes=5)
                            recent_connections = len([
                                a for a in self.connection_attempts[ip] if a > cutoff
                            ])
                        
                        if recent_connections > 0:
                            self._handle_suspicious_activity(ip, "persistent_activity", {
                                "recent_connections": recent_connections
                            })
                
                # Log security status
                status = self.get_security_status()
                logger.info("security_monitoring_status", status=status)
                
            except Exception as e:
                logger.error("security_monitoring_error", error=str(e))
            
            # Run every cleanup interval
            await asyncio.sleep(self.cleanup_interval_minutes * 60)
    
    async def start_monitoring(self):
        """Start security monitoring."""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_security())
            logger.info("security_monitoring_started")
    
    async def stop_monitoring(self):
        """Stop security monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                logger.info("security_monitoring_stopped")
            self.monitoring_task = None
    
    def block_ip(self, ip: str, reason: str = "manual"):
        """Manually block an IP address."""
        if not self.is_ip_allowed(ip):
            self.blocked_ips.add(ip)
            logger.info("ip_manually_blocked", ip=ip, reason=reason)
            
            # Schedule unblock
            asyncio.create_task(self._schedule_unblock(ip))
        else:
            logger.warning("cannot_block_allowed_ip", ip=ip)
    
    def unblock_ip(self, ip: str):
        """Manually unblock an IP address."""
        if ip in self.blocked_ips:
            self.blocked_ips.remove(ip)
            logger.info("ip_manually_unblocked", ip=ip)
        else:
            logger.warning("ip_not_blocked", ip=ip)
    
    def add_allowed_network(self, network: str):
        """Add a network to the allowlist."""
        try:
            network_obj = ipaddress.ip_network(network)
            self.allowed_networks.append(network_obj)
            logger.info("allowed_network_added", network=network)
        except ValueError as e:
            logger.error("invalid_network", network=network, error=str(e))
    
    def remove_allowed_network(self, network: str):
        """Remove a network from the allowlist."""
        try:
            network_obj = ipaddress.ip_network(network)
            if network_obj in self.allowed_networks:
                self.allowed_networks.remove(network_obj)
                logger.info("allowed_network_removed", network=network)
            else:
                logger.warning("network_not_in_allowlist", network=network)
        except ValueError as e:
            logger.error("invalid_network", network=network, error=str(e))


security_monitor = SecurityMonitor()

