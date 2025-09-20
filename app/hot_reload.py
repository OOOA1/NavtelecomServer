"""
Hot reload system for configurations and dictionaries.
"""
import asyncio
import signal
import hashlib
import yaml
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import structlog

from app.settings import settings

logger = structlog.get_logger()

@dataclass
class ReloadEvent:
    """Reload event definition."""
    timestamp: datetime
    event_type: str  # 'config', 'dict', 'all'
    file_path: Optional[str] = None
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None

class HotReloadManager:
    """Manages hot reloading of configurations and dictionaries."""
    
    def __init__(self):
        self.watched_files: Dict[str, str] = {}  # file_path -> hash
        self.reload_callbacks: List[Callable] = []
        self.dict_reload_callbacks: List[Callable] = []
        self.config_reload_callbacks: List[Callable] = []
        self.reload_history: List[ReloadEvent] = []
        self._running = False
        self._monitoring_task = None
        self._dry_run_mode = False
        
        # Files to watch
        self.config_files = [
            "config.yaml",
            "app/settings.py"
        ]
        
        self.dict_files = [
            "dicts/j1939.yaml",
            "dicts/obd2.yaml",
            "dicts/volvo.yaml",
            "dicts/scania.yaml"
        ]
    
    async def start(self):
        """Start hot reload monitoring."""
        if not self._running:
            self._running = True
            
            # Initialize file hashes
            await self._initialize_file_hashes()
            
            # Start monitoring task
            self._monitoring_task = asyncio.create_task(self._monitor_files())
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            logger.info("hot_reload_manager_started")
    
    async def stop(self):
        """Stop hot reload monitoring."""
        if self._running:
            self._running = False
            if self._monitoring_task:
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            logger.info("hot_reload_manager_stopped")
    
    def add_reload_callback(self, callback: Callable):
        """Add a callback for all reload events."""
        self.reload_callbacks.append(callback)
    
    def add_dict_reload_callback(self, callback: Callable):
        """Add a callback for dictionary reload events."""
        self.dict_reload_callbacks.append(callback)
    
    def add_config_reload_callback(self, callback: Callable):
        """Add a callback for config reload events."""
        self.config_reload_callbacks.append(callback)
    
    async def reload_dictionaries(self, dry_run: bool = False) -> Dict[str, Any]:
        """Reload all dictionaries."""
        self._dry_run_mode = dry_run
        
        try:
            event = ReloadEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="dict",
                file_path="all_dicts"
            )
            
            if dry_run:
                logger.info("dictionary_reload_dry_run_started")
                result = await self._dry_run_dict_reload()
            else:
                logger.info("dictionary_reload_started")
                result = await self._perform_dict_reload()
            
            event.success = result["success"]
            event.error_message = result.get("error_message")
            event.new_version = result.get("new_version")
            
            self.reload_history.append(event)
            
            if not dry_run and result["success"]:
                # Notify callbacks
                for callback in self.dict_reload_callbacks:
                    try:
                        await callback(result)
                    except Exception as e:
                        logger.error("dict_reload_callback_error", error=str(e))
                
                for callback in self.reload_callbacks:
                    try:
                        await callback(event)
                    except Exception as e:
                        logger.error("reload_callback_error", error=str(e))
            
            return result
            
        except Exception as e:
            logger.error("dictionary_reload_error", error=str(e))
            return {
                "success": False,
                "error_message": str(e),
                "changes": []
            }
    
    async def reload_config(self, dry_run: bool = False) -> Dict[str, Any]:
        """Reload configuration files."""
        self._dry_run_mode = dry_run
        
        try:
            event = ReloadEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="config",
                file_path="all_configs"
            )
            
            if dry_run:
                logger.info("config_reload_dry_run_started")
                result = await self._dry_run_config_reload()
            else:
                logger.info("config_reload_started")
                result = await self._perform_config_reload()
            
            event.success = result["success"]
            event.error_message = result.get("error_message")
            event.new_version = result.get("new_version")
            
            self.reload_history.append(event)
            
            if not dry_run and result["success"]:
                # Notify callbacks
                for callback in self.config_reload_callbacks:
                    try:
                        await callback(result)
                    except Exception as e:
                        logger.error("config_reload_callback_error", error=str(e))
                
                for callback in self.reload_callbacks:
                    try:
                        await callback(event)
                    except Exception as e:
                        logger.error("reload_callback_error", error=str(e))
            
            return result
            
        except Exception as e:
            logger.error("config_reload_error", error=str(e))
            return {
                "success": False,
                "error_message": str(e),
                "changes": []
            }
    
    async def reload_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """Reload all configurations and dictionaries."""
        self._dry_run_mode = dry_run
        
        try:
            event = ReloadEvent(
                timestamp=datetime.now(timezone.utc),
                event_type="all",
                file_path="all_files"
            )
            
            logger.info("full_reload_started", dry_run=dry_run)
            
            # Reload configs first
            config_result = await self.reload_config(dry_run)
            
            # Then reload dictionaries
            dict_result = await self.reload_dictionaries(dry_run)
            
            # Combine results
            success = config_result["success"] and dict_result["success"]
            error_message = None
            if not config_result["success"]:
                error_message = f"Config reload failed: {config_result.get('error_message')}"
            if not dict_result["success"]:
                if error_message:
                    error_message += f"; Dict reload failed: {dict_result.get('error_message')}"
                else:
                    error_message = f"Dict reload failed: {dict_result.get('error_message')}"
            
            event.success = success
            event.error_message = error_message
            
            self.reload_history.append(event)
            
            return {
                "success": success,
                "error_message": error_message,
                "config_result": config_result,
                "dict_result": dict_result
            }
            
        except Exception as e:
            logger.error("full_reload_error", error=str(e))
            return {
                "success": False,
                "error_message": str(e),
                "config_result": {"success": False},
                "dict_result": {"success": False}
            }
    
    async def _initialize_file_hashes(self):
        """Initialize file hashes for monitoring."""
        all_files = self.config_files + self.dict_files
        
        for file_path in all_files:
            try:
                if Path(file_path).exists():
                    hash_value = await self._calculate_file_hash(file_path)
                    self.watched_files[file_path] = hash_value
                    logger.debug("file_hash_initialized", file=file_path, hash=hash_value[:8])
            except Exception as e:
                logger.warning("file_hash_init_error", file=file_path, error=str(e))
    
    async def _monitor_files(self):
        """Monitor files for changes."""
        while self._running:
            try:
                await self._check_file_changes()
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("file_monitoring_error", error=str(e))
                await asyncio.sleep(10)
    
    async def _check_file_changes(self):
        """Check for file changes."""
        for file_path, old_hash in self.watched_files.items():
            try:
                if not Path(file_path).exists():
                    continue
                
                new_hash = await self._calculate_file_hash(file_path)
                if new_hash != old_hash:
                    logger.info("file_changed", file=file_path, old_hash=old_hash[:8], new_hash=new_hash[:8])
                    
                    # Update hash
                    self.watched_files[file_path] = new_hash
                    
                    # Determine reload type
                    if file_path in self.dict_files:
                        await self._handle_dict_change(file_path, old_hash, new_hash)
                    elif file_path in self.config_files:
                        await self._handle_config_change(file_path, old_hash, new_hash)
                        
            except Exception as e:
                logger.error("file_change_check_error", file=file_path, error=str(e))
    
    async def _handle_dict_change(self, file_path: str, old_hash: str, new_hash: str):
        """Handle dictionary file change."""
        logger.info("dictionary_file_changed", file=file_path)
        
        # Auto-reload dictionaries (but not configs)
        try:
            result = await self.reload_dictionaries(dry_run=False)
            if result["success"]:
                logger.info("dictionary_auto_reload_success", file=file_path)
            else:
                logger.error("dictionary_auto_reload_failed", file=file_path, error=result.get("error_message"))
        except Exception as e:
            logger.error("dictionary_auto_reload_error", file=file_path, error=str(e))
    
    async def _handle_config_change(self, file_path: str, old_hash: str, new_hash: str):
        """Handle config file change."""
        logger.info("config_file_changed", file=file_path)
        
        # Don't auto-reload configs, just log the change
        # Configs require manual reload for safety
        logger.warning("config_file_changed_manual_reload_required", file=file_path)
    
    async def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate file hash."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.error("file_hash_calculation_error", file=file_path, error=str(e))
            return ""
    
    async def _dry_run_dict_reload(self) -> Dict[str, Any]:
        """Dry run dictionary reload to see what would change."""
        changes = []
        
        for dict_file in self.dict_files:
            try:
                if not Path(dict_file).exists():
                    continue
                
                # Load current and new dictionaries
                with open(dict_file, 'r', encoding='utf-8') as f:
                    new_dict = yaml.safe_load(f)
                
                # Simulate parsing with new dictionary
                # This is a simplified check - in reality you'd test with sample data
                changes.append({
                    "file": dict_file,
                    "action": "reload",
                    "new_version": hashlib.md5(str(new_dict).encode()).hexdigest()[:8]
                })
                
            except Exception as e:
                changes.append({
                    "file": dict_file,
                    "action": "error",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "changes": changes,
            "new_version": hashlib.md5(str(changes).encode()).hexdigest()[:8]
        }
    
    async def _perform_dict_reload(self) -> Dict[str, Any]:
        """Actually reload dictionaries."""
        changes = []
        
        for dict_file in self.dict_files:
            try:
                if not Path(dict_file).exists():
                    continue
                
                # Reload dictionary
                with open(dict_file, 'r', encoding='utf-8') as f:
                    new_dict = yaml.safe_load(f)
                
                # Update the global can_parser
                from app.can_parser import can_parser
                can_parser._reload_dictionary(dict_file, new_dict)
                
                changes.append({
                    "file": dict_file,
                    "action": "reloaded",
                    "new_version": hashlib.md5(str(new_dict).encode()).hexdigest()[:8]
                })
                
            except Exception as e:
                changes.append({
                    "file": dict_file,
                    "action": "error",
                    "error": str(e)
                })
        
        success = all(change.get("action") != "error" for change in changes)
        
        return {
            "success": success,
            "changes": changes,
            "new_version": hashlib.md5(str(changes).encode()).hexdigest()[:8]
        }
    
    async def _dry_run_config_reload(self) -> Dict[str, Any]:
        """Dry run config reload."""
        changes = []
        
        for config_file in self.config_files:
            try:
                if not Path(config_file).exists():
                    continue
                
                # Simulate config reload
                changes.append({
                    "file": config_file,
                    "action": "would_reload",
                    "new_version": hashlib.md5(Path(config_file).read_bytes()).hexdigest()[:8]
                })
                
            except Exception as e:
                changes.append({
                    "file": config_file,
                    "action": "error",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "changes": changes,
            "new_version": hashlib.md5(str(changes).encode()).hexdigest()[:8]
        }
    
    async def _perform_config_reload(self) -> Dict[str, Any]:
        """Actually reload configuration."""
        # For now, just log that config reload was requested
        # In a real implementation, you'd reload the settings module
        logger.warning("config_reload_not_implemented", message="Config reload requires application restart")
        
        return {
            "success": False,
            "error_message": "Config reload requires application restart",
            "changes": []
        }
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for SIGHUP."""
        def sighup_handler(signum, frame):
            logger.info("sighup_received", signal=signum)
            asyncio.create_task(self.reload_all(dry_run=False))
        
        signal.signal(signal.SIGHUP, sighup_handler)
    
    def get_reload_history(self, limit: int = 50) -> List[ReloadEvent]:
        """Get reload history."""
        return self.reload_history[-limit:]
    
    def get_watched_files_status(self) -> Dict[str, str]:
        """Get status of watched files."""
        return self.watched_files.copy()

# Global hot reload manager instance
hot_reload_manager = HotReloadManager()
