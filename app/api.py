"""FastAPI application for telemetry data access."""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import structlog
import time

from app.db import get_db_session
from app.models import get_telemetry_by_device, get_raw_frames, get_can_raw_frames, get_can_signals
from app.metrics import get_metrics
from app.security import get_current_user, require_role, check_security
from app.slo import slo_manager
from app.reprocessing import reprocessing_manager
from app.hot_reload import hot_reload_manager
from app.canary import canary_manager

# Set up structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Navtelecom Server API",
    description="GPS/Telemetry data processing server",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request timing middleware
@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    # Record API latency
    slo_manager.record_measurement(
        "api_latency", process_time, response.status_code < 400, 
        operation=request.url.path
    )
    
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    try:
        # Check database connection
        from app.db import AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        
        # Check if services are running
        from app.tcp_server import decoder_service, batch_processor
        from app.alerts import alert_manager
        
        services_status = {
            "database": "healthy",
            "decoder_service": "running" if decoder_service.running else "stopped",
            "batch_processor": "running" if batch_processor.running else "stopped",
            "alert_manager": "running" if alert_manager.running else "stopped"
        }
        
        all_healthy = all(status in ["healthy", "running"] for status in services_status.values())
        
        return {
            "status": "ready" if all_healthy else "not_ready",
            "timestamp": datetime.utcnow().isoformat(),
            "services": services_status
        }
    except Exception as e:
        logger.error("readiness_check_error", error=str(e))
        return {
            "status": "not_ready",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@app.get("/stats")
async def get_stats():
    """Get server statistics."""
    # TODO: Implement statistics collection
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": {
            "active_connections": 0,
            "frames_processed": 0,
            "devices_active": 0
        }
    }


@app.get("/devices/{device_id}/telemetry")
async def get_device_telemetry(
    device_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    current_user: str = Depends(get_current_user),
    client_ip: str = Depends(check_security)
):
    """Get telemetry data for specific device."""
    try:
        telemetry = await get_telemetry_by_device(device_id, limit, offset)
        return {
            "device_id": device_id,
            "count": len(telemetry),
            "data": telemetry
        }
    except Exception as e:
        logger.error("telemetry_fetch_error", device_id=device_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/raw-frames")
async def get_raw_frames_endpoint(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session)
):
    """Get raw frames from database."""
    try:
        frames = await get_raw_frames(limit, offset)
        return {
            "count": len(frames),
            "data": frames
        }
    except Exception as e:
        logger.error("raw_frames_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/devices")
async def get_devices(db: AsyncSession = Depends(get_db_session)):
    """Get list of active devices."""
    # TODO: Implement device list
    return {
        "devices": [],
        "count": 0
    }


@app.get("/devices/{device_id}/can/raw")
async def get_device_can_raw(
    device_id: str,
    can_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    current_user: str = Depends(get_current_user),
    client_ip: str = Depends(check_security)
):
    """Get raw CAN frames for specific device."""
    try:
        frames = await get_can_raw_frames(device_id, can_id, limit, offset)
        return {
            "device_id": device_id,
            "can_id": can_id,
            "count": len(frames),
            "data": frames
        }
    except Exception as e:
        logger.error("can_raw_fetch_error", device_id=device_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/devices/{device_id}/can/signals")
async def get_device_can_signals(
    device_id: str,
    pgn: Optional[int] = None,
    spn: Optional[int] = None,
    mode: Optional[int] = None,
    pid: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    current_user: str = Depends(get_current_user),
    client_ip: str = Depends(check_security)
):
    """Get decoded CAN signals for specific device."""
    try:
        signals = await get_can_signals(device_id, pgn, spn, mode, pid, limit, offset)
        return {
            "device_id": device_id,
            "filters": {
                "pgn": pgn,
                "spn": spn,
                "mode": mode,
                "pid": pid
            },
            "count": len(signals),
            "data": signals
        }
    except Exception as e:
        logger.error("can_signals_fetch_error", device_id=device_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/can/signal-latest")
async def get_latest_can_signal(
    device_id: str,
    name: str,
    db: AsyncSession = Depends(get_db_session)
):
    """Get latest value of specific CAN signal."""
    try:
        signals = await get_can_signals(device_id, limit=1, offset=0)
        # Filter by signal name
        matching_signals = [s for s in signals if s.get("name") == name]
        
        if matching_signals:
            return {
                "device_id": device_id,
                "signal_name": name,
                "latest": matching_signals[0]
            }
        else:
            return {
                "device_id": device_id,
                "signal_name": name,
                "latest": None
            }
    except Exception as e:
        logger.error("can_signal_latest_error", device_id=device_id, signal_name=name, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/metrics")
async def get_prometheus_metrics():
    """Get Prometheus metrics."""
    try:
        metrics_data = get_metrics()
        return metrics_data
    except Exception as e:
        logger.error("metrics_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/alerts")
async def get_active_alerts(
    current_user: str = Depends(require_role("admin"))
):
    """Get active alerts."""
    try:
        from app.alerts import alert_manager
        alerts = alert_manager.get_active_alerts()
        return {
            "alerts": [
                {
                    "name": alert.name,
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp,
                    "labels": alert.labels,
                    "value": alert.value,
                    "threshold": alert.threshold
                }
                for alert in alerts
            ],
            "count": len(alerts)
        }
    except Exception as e:
        logger.error("alerts_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/slo")
async def get_slo_status(
    current_user: str = Depends(require_role("admin"))
):
    """Get SLO status for all targets."""
    try:
        slo_status = {}
        for target_name in slo_manager.slo_targets.keys():
            slo_status[target_name] = slo_manager.get_current_slo_status(target_name)
        
        return {
            "slo_status": slo_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("slo_status_fetch_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/slo/{target_name}")
async def get_slo_target_status(
    target_name: str,
    current_user: str = Depends(require_role("admin"))
):
    """Get SLO status for specific target."""
    try:
        if target_name not in slo_manager.slo_targets:
            raise HTTPException(status_code=404, detail="SLO target not found")
        
        return {
            "slo_status": slo_manager.get_current_slo_status(target_name),
            "burn_rate": slo_manager.check_burn_rate(target_name),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("slo_target_status_fetch_error", target=target_name, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/reprocessing/jobs")
async def list_reprocessing_jobs(
    current_user: str = Depends(require_role("admin"))
):
    """List all reprocessing jobs."""
    try:
        jobs = await reprocessing_manager.list_jobs()
        return {
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "description": job.description,
                    "dict_version": job.dict_version,
                    "status": job.status,
                    "progress": job.progress,
                    "total_records": job.total_records,
                    "processed_records": job.processed_records,
                    "error_count": job.error_count,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "error_message": job.error_message
                }
                for job in jobs
            ]
        }
    except Exception as e:
        logger.error("reprocessing_jobs_list_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reprocessing/jobs")
async def create_reprocessing_job(
    name: str,
    description: str,
    device_ids: Optional[List[str]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    batch_size: int = 1000,
    current_user: str = Depends(require_role("admin"))
):
    """Create a new reprocessing job."""
    try:
        job_id = await reprocessing_manager.create_reprocessing_job(
            name=name,
            description=description,
            device_ids=device_ids,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size
        )
        
        return {
            "job_id": job_id,
            "message": "Reprocessing job created successfully"
        }
    except Exception as e:
        logger.error("reprocessing_job_create_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reprocessing/jobs/{job_id}/start")
async def start_reprocessing_job(
    job_id: str,
    current_user: str = Depends(require_role("admin"))
):
    """Start a reprocessing job."""
    try:
        success = await reprocessing_manager.start_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        
        return {"message": "Reprocessing job started successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reprocessing_job_start_error", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/reprocessing/jobs/{job_id}/cancel")
async def cancel_reprocessing_job(
    job_id: str,
    current_user: str = Depends(require_role("admin"))
):
    """Cancel a reprocessing job."""
    try:
        success = await reprocessing_manager.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or not running")
        
        return {"message": "Reprocessing job cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reprocessing_job_cancel_error", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/reprocessing/jobs/{job_id}")
async def get_reprocessing_job_status(
    job_id: str,
    current_user: str = Depends(require_role("admin"))
):
    """Get reprocessing job status."""
    try:
        job = await reprocessing_manager.get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return {
            "id": job.id,
            "name": job.name,
            "description": job.description,
            "dict_version": job.dict_version,
            "status": job.status,
            "progress": job.progress,
            "total_records": job.total_records,
            "processed_records": job.processed_records,
            "error_count": job.error_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reprocessing_job_status_error", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/admin/reload-dicts")
async def reload_dictionaries(
    dry_run: bool = False,
    current_user: str = Depends(require_role("admin"))
):
    """Reload dictionaries with optional dry run."""
    try:
        result = await hot_reload_manager.reload_dictionaries(dry_run=dry_run)
        
        return {
            "success": result["success"],
            "dry_run": dry_run,
            "changes": result.get("changes", []),
            "error_message": result.get("error_message"),
            "new_version": result.get("new_version"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("reload_dictionaries_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/admin/reload-config")
async def reload_config(
    dry_run: bool = False,
    current_user: str = Depends(require_role("admin"))
):
    """Reload configuration with optional dry run."""
    try:
        result = await hot_reload_manager.reload_config(dry_run=dry_run)
        
        return {
            "success": result["success"],
            "dry_run": dry_run,
            "changes": result.get("changes", []),
            "error_message": result.get("error_message"),
            "new_version": result.get("new_version"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("reload_config_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/admin/reload-all")
async def reload_all(
    dry_run: bool = False,
    current_user: str = Depends(require_role("admin"))
):
    """Reload all configurations and dictionaries."""
    try:
        result = await hot_reload_manager.reload_all(dry_run=dry_run)
        
        return {
            "success": result["success"],
            "dry_run": dry_run,
            "config_result": result.get("config_result", {}),
            "dict_result": result.get("dict_result", {}),
            "error_message": result.get("error_message"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("reload_all_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/admin/reload-history")
async def get_reload_history(
    limit: int = 50,
    current_user: str = Depends(require_role("admin"))
):
    """Get reload history."""
    try:
        history = hot_reload_manager.get_reload_history(limit)
        
        return {
            "history": [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type,
                    "file_path": event.file_path,
                    "old_version": event.old_version,
                    "new_version": event.new_version,
                    "success": event.success,
                    "error_message": event.error_message
                }
                for event in history
            ],
            "count": len(history)
        }
    except Exception as e:
        logger.error("reload_history_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/admin/watched-files")
async def get_watched_files_status(
    current_user: str = Depends(require_role("admin"))
):
    """Get status of watched files."""
    try:
        status = hot_reload_manager.get_watched_files_status()
        
        return {
            "watched_files": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("watched_files_status_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/canary/configs")
async def get_canary_configs(
    current_user: str = Depends(require_role("admin"))
):
    """Get all canary configurations."""
    try:
        configs = canary_manager.list_canary_configs()
        return {
            "canary_configs": [
                {
                    "name": config.name,
                    "strategy": config.strategy.value,
                    "percentage": config.percentage,
                    "device_ids": list(config.device_ids) if config.device_ids else [],
                    "enabled": config.enabled,
                    "created_at": config.created_at.isoformat() if config.created_at else None,
                    "updated_at": config.updated_at.isoformat() if config.updated_at else None
                }
                for config in configs.values()
            ]
        }
    except Exception as e:
        logger.error("canary_configs_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/canary/configs")
async def create_canary_config(
    name: str,
    strategy: str,
    percentage: float = 0.0,
    device_ids: Optional[List[str]] = None,
    enabled: bool = False,
    current_user: str = Depends(require_role("admin"))
):
    """Create a new canary configuration."""
    try:
        from app.canary import CanaryStrategy
        
        strategy_enum = CanaryStrategy(strategy)
        success = await canary_manager.create_canary_config(
            name=name,
            strategy=strategy_enum,
            percentage=percentage,
            device_ids=set(device_ids) if device_ids else None,
            enabled=enabled
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to create canary config")
        
        return {"message": "Canary configuration created successfully"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid strategy")
    except Exception as e:
        logger.error("canary_config_create_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.put("/canary/configs/{name}")
async def update_canary_config(
    name: str,
    percentage: Optional[float] = None,
    device_ids: Optional[List[str]] = None,
    enabled: Optional[bool] = None,
    current_user: str = Depends(require_role("admin"))
):
    """Update canary configuration."""
    try:
        success = await canary_manager.update_canary_config(
            name=name,
            percentage=percentage,
            device_ids=set(device_ids) if device_ids else None,
            enabled=enabled
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Canary config not found")
        
        return {"message": "Canary configuration updated successfully"}
    except Exception as e:
        logger.error("canary_config_update_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/canary/metrics/{canary_name}")
async def get_canary_metrics(
    canary_name: str,
    limit: int = 1000,
    current_user: str = Depends(require_role("admin"))
):
    """Get canary deployment metrics."""
    try:
        metrics = canary_manager.get_canary_metrics(canary_name, limit)
        summary = canary_manager.get_canary_summary(canary_name)
        
        return {
            "canary_name": canary_name,
            "summary": summary,
            "recent_metrics": [
                {
                    "device_id": m.device_id,
                    "timestamp": m.timestamp.isoformat(),
                    "success": m.success,
                    "latency_ms": m.latency_ms,
                    "error_message": m.error_message,
                    "feature_version": m.feature_version
                }
                for m in metrics[-100:]  # Last 100 metrics
            ]
        }
    except Exception as e:
        logger.error("canary_metrics_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/canary/feature-flags")
async def get_feature_flags(
    current_user: str = Depends(require_role("admin"))
):
    """Get all feature flags."""
    try:
        flags = canary_manager.get_feature_flags()
        return {
            "feature_flags": flags,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("feature_flags_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/canary/feature-flags/{feature_name}")
async def set_feature_flag(
    feature_name: str,
    enabled: bool,
    current_user: str = Depends(require_role("admin"))
):
    """Set feature flag value."""
    try:
        success = canary_manager.set_feature_flag(feature_name, enabled)
        if not success:
            raise HTTPException(status_code=404, detail="Feature flag not found")
        
        return {"message": f"Feature flag {feature_name} set to {enabled}"}
    except Exception as e:
        logger.error("feature_flag_set_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/canary/shadow-configs")
async def get_shadow_configs(
    current_user: str = Depends(require_role("admin"))
):
    """Get all shadow traffic configurations."""
    try:
        configs = canary_manager.list_shadow_configs()
        return {
            "shadow_configs": [
                {
                    "name": config.name,
                    "target_url": config.target_url,
                    "percentage": config.percentage,
                    "device_ids": list(config.device_ids) if config.device_ids else [],
                    "enabled": config.enabled,
                    "timeout_ms": config.timeout_ms,
                    "retry_count": config.retry_count,
                    "created_at": config.created_at.isoformat() if config.created_at else None,
                    "updated_at": config.updated_at.isoformat() if config.updated_at else None
                }
                for config in configs.values()
            ]
        }
    except Exception as e:
        logger.error("shadow_configs_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/alerts/{alert_name}/resolve")
async def resolve_alert(
    alert_name: str,
    current_user: str = Depends(require_role("admin"))
):
    """Resolve an alert."""
    try:
        from app.alerts import alert_manager
        alert_manager.resolve_alert(alert_name)
        return {"status": "resolved", "alert_name": alert_name}
    except Exception as e:
        logger.error("alert_resolve_error", alert_name=alert_name, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    from app.settings import settings
    
    uvicorn.run(
        "app.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
