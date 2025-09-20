"""
Main API application with versioning support.
"""
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
import time
import uuid

from app.api.v1.routers import devices as v1_devices
from app.api.v2.routers import devices as v2_devices
from app.api.middleware.idempotency import idempotency_middleware
from app.api.deps import get_trace_id, get_canary_flag, get_api_version

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Navtel API",
    description="Navtel telematics data API with versioning support",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add idempotency middleware
app.middleware("http")(idempotency_middleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def add_trace_id_header(request: Request, call_next):
    """Add trace ID header."""
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


@app.middleware("http")
async def add_api_version_header(request: Request, call_next):
    """Add API version header."""
    api_version = get_api_version(request)
    response = await call_next(request)
    response.headers["X-API-Version"] = api_version
    return response


@app.middleware("http")
async def add_deprecation_headers(request: Request, call_next):
    """Add deprecation headers for v1."""
    response = await call_next(request)
    
    if request.url.path.startswith("/api/v1/"):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "2025-12-31T23:59:59Z"
        response.headers["Link"] = "</api/v2/>; rel=\"successor-version\""
    
    return response


# Include routers
app.include_router(v1_devices.router, prefix="/api/v1")
app.include_router(v2_devices.router, prefix="/api/v2")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Navtel API",
        "version": "2.0.0",
        "docs": "/docs",
        "v1": "/api/v1",
        "v2": "/api/v2"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "2.0.0"
    }


@app.get("/api/v1/openapi.json")
async def v1_openapi():
    """Get OpenAPI spec for v1."""
    # This would return the v1 OpenAPI spec
    return {"message": "v1 OpenAPI spec"}


@app.get("/api/v2/openapi.json")
async def v2_openapi():
    """Get OpenAPI spec for v2."""
    # This would return the v2 OpenAPI spec
    return {"message": "v2 OpenAPI spec"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    
    logger.error("global_exception", 
                error=str(exc), 
                trace_id=trace_id,
                path=request.url.path,
                method=request.method)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal error occurred",
                "trace_id": trace_id
            }
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

