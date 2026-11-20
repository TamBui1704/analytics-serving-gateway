"""
Tests for Analytics & Branding APIs (Option A: Decentralized Auth).
"""

import os
import time
import hashlib
import pytest
from unittest.mock import AsyncMock, patch

# Đặt biến môi trường riêng cho bài test
os.environ["ANALYTICS_API_KEYS"] = "key_user_a,key_user_vip,demo-key-123"
os.environ["BRANDING_API_KEYS"] = "key_user_b,key_user_vip"

from fastapi.testclient import TestClient
from api_app.main import app

client = TestClient(app)

KEY_A = "key_user_a"
KEY_B = "key_user_b"
KEY_VIP = "key_user_vip"
INVALID_KEY = "bad-key"

MOCK_DAILY = [
    {
        "order_date": "2026-11-01",
        "total_orders": 100,
        "total_revenue": 5000.0,
        "avg_order_value": 50.0,
    }
]

# ── Health Probes ─────────────────────────────────────────────────────────────

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


# ── Analytics Service Authentication Tests ────────────────────────────────────

def test_missing_credentials_returns_401():
    resp = client.get("/api/v1/sales/daily")
    assert resp.status_code == 401


def test_invalid_token_returns_401():
    now = str(int(time.time()))
    resp = client.get(
        "/api/v1/sales/daily",
        headers={"Timestamp": now, "Authorization": "Bearer bad_invalid_token_123"},
    )
    assert resp.status_code == 401


def test_client_a_sha256_success_on_analytics():
    now = str(int(time.time()))
    token = hashlib.sha256(f"{KEY_A}{now}".encode()).hexdigest()
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_DAILY):
        resp = client.get(
            "/api/v1/sales/daily",
            headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


def test_client_a_rejected_on_branding():
    # Khách A không có key trong BRANDING_API_KEYS
    now = str(int(time.time()))
    token = hashlib.sha256(f"{KEY_A}{now}".encode()).hexdigest()
    resp = client.get(
        "/api/v1/branding/overview",
        headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_client_b_success_on_branding():
    now = str(int(time.time()))
    token = hashlib.sha256(f"{KEY_B}{now}".encode()).hexdigest()
    resp = client.get(
        "/api/v1/branding/overview",
        headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_client_b_rejected_on_analytics():
    now = str(int(time.time()))
    token = hashlib.sha256(f"{KEY_B}{now}".encode()).hexdigest()
    resp = client.get(
        "/api/v1/sales/daily",
        headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_client_vip_success_on_both():
    now = str(int(time.time()))
    token = hashlib.sha256(f"{KEY_VIP}{now}".encode()).hexdigest()

    # VIP vào Analytics -> OK
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_DAILY):
        resp_a = client.get(
            "/api/v1/sales/daily",
            headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
        )
    assert resp_a.status_code == 200

    # VIP vào Branding -> OK
    resp_b = client.get(
        "/api/v1/branding/overview",
        headers={"Timestamp": now, "Authorization": f"Bearer {token}"},
    )
    assert resp_b.status_code == 200


def test_expired_timestamp_rejected():
    expired_ts = str(int(time.time()) - 120)  # Quá 60 giây
    token = hashlib.sha256(f"{KEY_A}{expired_ts}".encode()).hexdigest()
    resp = client.get(
        "/api/v1/sales/daily",
        headers={"Timestamp": expired_ts, "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()
