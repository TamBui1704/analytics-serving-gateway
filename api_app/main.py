"""
Analytics Serving Gateway - FastAPI Application
Entry point: starts server, registers routers, adds middleware
"""

import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from api_app.database import ping_clickhouse
from api_app.routers import analytics, branding

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("analytics-gateway")

# Audit logger riêng xuất JSON thuần 1 dòng/request để Loki/Grafana tự parse thành các cột
audit_logger = logging.getLogger("analytics-audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False
_audit_handler = logging.StreamHandler()
_audit_handler.setFormatter(logging.Formatter("%(message)s"))
audit_logger.addHandler(_audit_handler)

VN_TZ = timezone(timedelta(hours=7))
MAX_LOG_BODY_LEN = 1000
_SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "authorization"}
_ERROR_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _mask_sensitive(data):
    """Che thông tin nhạy cảm trong request body trước khi ghi log."""
    if isinstance(data, dict):
        return {
            k: ("***" if k.lower() in _SENSITIVE_KEYS else _mask_sensitive(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive(item) for item in data]
    return data


def _safe_parse_body(raw_bytes: bytes, mask: bool = False):
    """Parse JSON hoặc text và cắt gọn tối đa MAX_LOG_BODY_LEN ký tự."""
    if not raw_bytes:
        return None
    text = raw_bytes.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
        if mask:
            parsed = _mask_sensitive(parsed)
        serialized = json.dumps(parsed, ensure_ascii=False)
        if len(serialized) > MAX_LOG_BODY_LEN:
            return serialized[:MAX_LOG_BODY_LEN] + "... [truncated]"
        return parsed
    except (json.JSONDecodeError, TypeError):
        if len(text) > MAX_LOG_BODY_LEN:
            return text[:MAX_LOG_BODY_LEN] + "... [truncated]"
        return text

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

# ── Structured JSON Audit Logging middleware ──────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Bỏ qua các endpoint probe/metrics để tránh spam log và giảm overhead
    if request.url.path in ("/healthz", "/readyz", "/metrics"):
        return await call_next(request)

    started_dt = datetime.now(VN_TZ)
    start_perf = time.perf_counter()

    req_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:12]
    is_via_gateway = bool(request.headers.get("x-forwarded-proto") or request.headers.get("x-real-ip"))
    entry_point = "gateway" if is_via_gateway else "direct"
    client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "-")
    user_agent = request.headers.get("user-agent", "-")

    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    query_str = f"?{request.url.query}" if request.url.query else ""
    full_url = f"{scheme}://{host}{request.url.path}{query_str}"

    # Đọc tham số đầu vào: query params + body (nếu có)
    req_body_bytes = await request.body()
    request_params = {
        "query": dict(request.query_params),
        "body": _safe_parse_body(req_body_bytes, mask=True),
    }

    error_detail = None
    res_body_bytes = b""

    try:
        response = await call_next(request)
        # Thu lại nội dung response để ghi audit log rồi trả nguyên vẹn cho client
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        res_body_bytes = b"".join(chunks)
        status_code = response.status_code

        # Tạo lại headers, bỏ content-length cũ để Starlette tự tính lại nếu body lỗi được bổ sung trường
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        headers["X-Request-ID"] = req_id

        # Chuẩn Production: mọi lỗi 4xx/5xx đều trả JSON chuẩn kèm request_id để user gửi đội hạ tầng tra cứu
        if status_code >= 400:
            error_detail = _safe_parse_body(res_body_bytes)
            err_timestamp = datetime.now(VN_TZ).isoformat(timespec="milliseconds")
            detail_val = (
                error_detail.get("detail", error_detail)
                if isinstance(error_detail, dict)
                else (error_detail or "Request failed")
            )
            standardized_error = {
                "error_code": _ERROR_CODE_MAP.get(status_code, f"HTTP_{status_code}"),
                "detail": detail_val,
                "request_id": req_id,
                "timestamp": err_timestamp,
                "path": request.url.path,
            }
            rebuilt_response = JSONResponse(
                status_code=status_code,
                content=standardized_error,
                headers=headers,
            )
            res_body_bytes = rebuilt_response.body
        else:
            rebuilt_response = Response(
                content=res_body_bytes,
                status_code=status_code,
                headers=headers,
                media_type=response.media_type,
            )
    except Exception:  # noqa: BLE001
        status_code = 500
        error_detail = traceback.format_exc()
        err_timestamp = datetime.now(VN_TZ).isoformat(timespec="milliseconds")
        rebuilt_response = JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "detail": "Internal Server Error",
                "request_id": req_id,
                "timestamp": err_timestamp,
                "path": request.url.path,
            },
            headers={"X-Request-ID": req_id},
        )
        res_body_bytes = rebuilt_response.body

    finished_dt = datetime.now(VN_TZ)
    duration_ms = round((time.perf_counter() - start_perf) * 1000, 1)

    level = "ERROR" if status_code >= 500 else ("WARNING" if status_code >= 400 else "INFO")
    audit_record = {
        "level": level,
        "request_id": req_id,
        "entry_point": entry_point,
        "started_at": started_dt.isoformat(timespec="milliseconds"),
        "finished_at": finished_dt.isoformat(timespec="milliseconds"),
        "duration_ms": duration_ms,
        "client_ip": client_ip,
        "method": request.method,
        "path": request.url.path,
        "full_url": full_url,
        "status_code": status_code,
        "request_params": request_params,
        "response_size_bytes": len(res_body_bytes),
        "response_body": _safe_parse_body(res_body_bytes),
        "error_detail": error_detail,
        "user_agent": user_agent,
    }
    audit_logger.info(json.dumps(audit_record, ensure_ascii=False))
    return rebuilt_response

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics Service"])
app.include_router(branding.router, prefix="/api/v1", tags=["Branding Service"])

# ── Prometheus Metrics (/metrics) ──────────────────────────────────────────────
Instrumentator(
    should_group_status_codes=False,
    excluded_handlers=["/metrics", "/healthz", "/readyz"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

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
