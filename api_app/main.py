"""
Analytics Serving Gateway - FastAPI Application
Entry point: starts server, registers routers, adds middleware
"""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
import os
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
    # Tắt docs mặc định để tự phục vụ file JS/CSS từ CDN Swagger (không phụ thuộc mạng)
    docs_url=None,
    redoc_url=None,
)

# ── CORS (Whitelist có thể cấu hình qua biến môi trường) ──────────────────────
# Hỗ trợ máy local phát triển và dễ dàng override khi có domain production
_DEFAULT_CORS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://analytics.local"
cors_origins_raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS)
allowed_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Client-Key", "Authorization"],
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

# ── Docs tự phục vụ (không phụ thuộc CDN bên ngoài) ──────────────────────────
# FastAPI mặc định dùng CDN jsdelivr.net cho ReDoc — dễ bị trắng trang khi mạng chậm.
# Giải pháp: tắt docs mặc định (docs_url=None) và tự định nghĩa route,
# trỏ sang CDN dự phòng hoặc dùng CDN Swagger (vốn đã được FastAPI bundle sẵn).
@app.get("/docs", include_in_schema=False)
async def custom_swagger() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " – Swagger UI",
        # FastAPI bundle sẵn Swagger JS nội bộ nên không cần ra ngoài mạng
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc() -> HTMLResponse:
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=app.title + " – ReDoc",
        # Dùng bản cố định thay vì "@next" (tránh auto-upgrade gây lỗi)
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


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

