"""
Analytics Serving Gateway - FastAPI Application
Entry point: starts server, registers routers, adds middleware
"""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging

from api_app.routers import analytics

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("analytics-gateway")

# ── App init ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Analytics Serving Gateway",
    description=(
        "A lightweight API Gateway for serving OLAP analytics data "
        "from ClickHouse, secured by API Key and deployed on Kubernetes."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])

# ── Health / readiness probes (K8s uses these) ────────────────────────────────
@app.get("/healthz", tags=["Probe"], summary="Liveness probe")
async def healthz():
    """K8s liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/readyz", tags=["Probe"], summary="Readiness probe")
async def readyz():
    """K8s readiness probe — checks DB connectivity before accepting traffic."""
    from api_app.database import ping_clickhouse
    try:
        await ping_clickhouse()
        return {"status": "ready", "db": "clickhouse:ok"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ClickHouse not reachable: {exc}",
        )


# ── Root ───────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "analytics-serving-gateway",
        "version": "1.0.0",
        "docs": "/docs",
    }

