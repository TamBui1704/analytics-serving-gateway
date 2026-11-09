"""
Tests for Analytics Serving Gateway API.

Uses httpx.AsyncClient with TestClient so no real ClickHouse is needed.
ClickHouse calls are mocked via pytest monkeypatch.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from api_app.main import app

client = TestClient(app)

VALID_KEY = "demo-key-123"
INVALID_KEY = "bad-key"


# ── Health probes ──────────────────────────────────────────────────────────────
def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_ok():
    with patch("api_app.database.ping_clickhouse", new_callable=AsyncMock):
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["db"] == "clickhouse:ok"


def test_readyz_db_down():
    with patch("api_app.database.ping_clickhouse", side_effect=ConnectionError("down")):
        resp = client.get("/readyz")
    assert resp.status_code == 503


# ── API Key auth ───────────────────────────────────────────────────────────────
def test_missing_api_key_returns_401():
    resp = client.get("/api/v1/sales/daily")
    assert resp.status_code == 401


def test_invalid_api_key_returns_401():
    resp = client.get("/api/v1/sales/daily", headers={"X-API-Key": INVALID_KEY})
    assert resp.status_code == 401


# ── Analytics endpoints (mocked DB) ───────────────────────────────────────────
MOCK_DAILY = [
    {
        "order_date": "2026-11-01",
        "total_orders": 100,
        "total_revenue": 5000.0,
        "avg_order_value": 50.0,
    }
]

MOCK_PRODUCTS = [
    {
        "product_name": "Laptop Pro",
        "category": "Electronics",
        "units_sold": 20,
        "revenue": 40000.0,
    }
]

MOCK_REGIONS = [
    {
        "region": "Asia Pacific",
        "total_orders": 300,
        "total_revenue": 15000.0,
        "unique_customers": 250,
    }
]


def test_daily_sales_valid_key():
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_DAILY):
        resp = client.get("/api/v1/sales/daily", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["total_orders"] == 100


def test_top_products_valid_key():
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_PRODUCTS):
        resp = client.get("/api/v1/products/top", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.json()[0]["product_name"] == "Laptop Pro"


def test_region_summary_valid_key():
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=MOCK_REGIONS):
        resp = client.get("/api/v1/regions/summary", headers={"X-API-Key": VALID_KEY})
    assert resp.status_code == 200
    assert resp.json()[0]["region"] == "Asia Pacific"


def test_daily_sales_days_param_validation():
    """days param must be 1–90."""
    with patch("api_app.database.query", new_callable=AsyncMock, return_value=[]):
        resp = client.get(
            "/api/v1/sales/daily?days=200", headers={"X-API-Key": VALID_KEY}
        )
    assert resp.status_code == 422   # FastAPI validation error

