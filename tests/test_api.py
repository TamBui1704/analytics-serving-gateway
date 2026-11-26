"""
QA & Security Test Suite for Analytics & Branding APIs (HMAC-SHA256 Auth + Audit Schema).
"""

import hashlib
import hmac
import os
import time
from unittest.mock import AsyncMock, patch

# Đặt biến môi trường riêng cho bài test
os.environ["ANALYTICS_API_KEYS"] = "key_user_a,key_user_vip,demo-key-123"
os.environ["BRANDING_API_KEYS"] = "key_user_b,key_user_vip"

from fastapi.testclient import TestClient

from api_app.main import _mask_sensitive, app

client = TestClient(app)

KEY_A = "key_user_a"
KEY_B = "key_user_b"
KEY_VIP = "key_user_vip"

MOCK_DAILY = [
    {
        "order_date": "2026-11-01",
        "total_orders": 100,
        "total_revenue": 5000.0,
        "avg_order_value": 50.0,
    }
]


def _make_hmac_headers(secret_key: str, method: str, path: str, ts: str | None = None) -> dict[str, str]:
    """Tạo header Timestamp + HMAC-SHA256(key, METHOD:PATH:TIMESTAMP)."""
    now = ts or str(int(time.time()))
    canonical = f"{method.upper()}:{path}:{now}".encode("utf-8")
    sig = hmac.new(secret_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return {"Timestamp": now, "Authorization": f"Bearer {sig}"}


# ── 1. Health & Metrics Probes ────────────────────────────────────────────────

def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_ok():
    with patch("api_app.main.ping_clickhouse", new_callable=AsyncMock):
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["db"] == "clickhouse:ok"


def test_readyz_db_down():
    with patch("api_app.main.ping_clickhouse", side_effect=ConnectionError("down")):
        resp = client.get("/readyz")
    assert resp.status_code == 503


def test_metrics_endpoint_exposes_prometheus_counters():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text or "process_cpu_seconds_total" in resp.text


# ── 2. HMAC-SHA256 Authentication & Authorization ─────────────────────────────

def test_missing_credentials_returns_standardized_401():
    resp = client.get("/api/v1/sales/daily")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error_code"] == "UNAUTHORIZED"
    assert "request_id" in body and len(body["request_id"]) > 0
    assert "timestamp" in body
    assert body["path"] == "/api/v1/sales/daily"
    assert resp.headers.get("x-request-id") == body["request_id"]


def test_invalid_signature_returns_401():
    now = str(int(time.time()))
    resp = client.get(
        "/api/v1/sales/daily",
        headers={"Timestamp": now, "Authorization": "Bearer bad_invalid_signature_123"},
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "UNAUTHORIZED"


def test_expired_timestamp_rejected_401():
    expired_ts = str(int(time.time()) - 120)  # Quá cửa sổ ±60s
    headers = _make_hmac_headers(KEY_A, "GET", "/api/v1/sales/daily", ts=expired_ts)
    resp = client.get("/api/v1/sales/daily", headers=headers)
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_cross_endpoint_token_replay_blocked_401():
    """Chữ ký cho /api/v1/sales/daily KHÔNG được phép dùng lại cho /api/v1/products/top."""
    headers = _make_hmac_headers(KEY_A, "GET", "/api/v1/sales/daily")
    resp = client.get("/api/v1/products/top", headers=headers)
    assert resp.status_code == 401


def test_client_a_hmac_success_on_analytics():
    headers = _make_hmac_headers(KEY_A, "GET", "/api/v1/sales/daily")
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_DAILY):
        resp = client.get("/api/v1/sales/daily", headers=headers)
    assert resp.status_code == 200
    assert resp.json()[0]["total_orders"] == 100


def test_client_a_rejected_on_branding():
    headers = _make_hmac_headers(KEY_A, "GET", "/api/v1/branding/overview")
    resp = client.get("/api/v1/branding/overview", headers=headers)
    assert resp.status_code == 401


def test_client_b_success_on_branding_without_leaking_secret_key():
    headers = _make_hmac_headers(KEY_B, "GET", "/api/v1/branding/overview")
    resp = client.get("/api/v1/branding/overview", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # Bảo mật P0: response KHÔNG ĐƯỢC chứa bất kỳ phần nào của secret_key gốc
    assert KEY_B not in str(body)
    assert KEY_B[:8] not in str(body)
    assert body["authenticated_client"].startswith("client_branding_")


def test_client_b_rejected_on_analytics():
    headers = _make_hmac_headers(KEY_B, "GET", "/api/v1/sales/daily")
    resp = client.get("/api/v1/sales/daily", headers=headers)
    assert resp.status_code == 401


def test_client_vip_success_on_both():
    headers_a = _make_hmac_headers(KEY_VIP, "GET", "/api/v1/sales/daily")
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_DAILY):
        resp_a = client.get("/api/v1/sales/daily", headers=headers_a)
    assert resp_a.status_code == 200

    headers_b = _make_hmac_headers(KEY_VIP, "GET", "/api/v1/branding/overview")
    resp_b = client.get("/api/v1/branding/overview", headers=headers_b)
    assert resp_b.status_code == 200


# ── 3. Validation & Sensitive Data Masking ────────────────────────────────────

def test_query_param_out_of_range_returns_422():
    headers = _make_hmac_headers(KEY_A, "GET", "/api/v1/sales/daily")
    resp = client.get("/api/v1/sales/daily?days=999", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "VALIDATION_ERROR"
    assert "request_id" in resp.json()


def test_mask_sensitive_hides_secrets_recursively():
    payload = {
        "username": "tambt",
        "password": "super-secret-password",
        "nested": {"api_key": "k_12345", "token": "tok_999", "safe": "ok"},
    }
    masked = _mask_sensitive(payload)
    assert masked["username"] == "tambt"
    assert masked["password"] == "***"
    assert masked["nested"]["api_key"] == "***"
    assert masked["nested"]["token"] == "***"
    assert masked["nested"]["safe"] == "ok"
