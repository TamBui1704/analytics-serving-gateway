"""
Analytics Serving Gateway - FastAPI Application
Entry point: starts server, registers routers, adds middleware
"""

import logging
import os
import time

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from api_app.database import ping_clickhouse
from api_app.routers import analytics, branding

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("analytics-gateway")

# ── App init ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Analytics Serving Gateway",
    description="Serving OLAP analytics data from ClickHouse and Branding APIs, secured by SHA-256 signing.",
    version="2.1.0",
    docs_url=None,
    redoc_url=None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
_DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,https://analytics.local:8443,https://branding.local:8443"
cors_origins_raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS)
allowed_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Timestamp",
        "X-Timestamp",
        "Authorization",
        "X-API-Key",
        "X-Client-Key",
        "X-Target-Service",
        "X-User-Id",
    ],
)

# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    # Chuẩn Production: Mute log của health probe nếu 200 OK để chống spam log
    if request.url.path in ("/healthz", "/readyz") and response.status_code == 200:
        return response

    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics Service"])
app.include_router(branding.router, prefix="/api/v1", tags=["Branding Service"])

# ── Docs tự phục vụ (không phụ thuộc CDN bên ngoài) ──────────────────────────
@app.get("/docs", include_in_schema=False)
async def custom_swagger() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " – Swagger UI",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc() -> HTMLResponse:
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=app.title + " – ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


# ── Health / readiness probes (K8s uses these) ────────────────────────────────
@app.get("/healthz", tags=["Probe"], summary="Liveness probe")
async def healthz():
    """K8s liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/readyz", tags=["Probe"], summary="Readiness probe")
async def readyz():
    """K8s readiness probe — checks ClickHouse before accepting traffic."""
    try:
        await ping_clickhouse()
        return {"status": "ready", "db": "clickhouse:ok"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ClickHouse unreachable: {exc}",
        )


# ── Root ───────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "analytics-serving-gateway",
        "version": "2.1.0",
        "docs": "/docs",
    }
