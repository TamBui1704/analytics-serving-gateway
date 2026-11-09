"""
Analytics router — all business endpoints live here.

API Key authentication is handled at two levels:
  1. NGINX Ingress (rate limit + header presence check) — infra level.
  2. This dependency (validate key value)                — app level.

This double-layer is a good learning example of "defence in depth".
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from api_app import database

router = APIRouter()

# ── API Key validation ─────────────────────────────────────────────────────────
# In production: store hashed keys in DB / Vault.
# For learning: a simple env-var set is fine.
import os

_VALID_KEYS: set[str] = set(
    filter(None, os.getenv("API_KEYS", "demo-key-123,demo-key-456").split(","))
)


async def require_api_key(x_api_key: Annotated[str | None, Header()] = None):
    """
    FastAPI dependency that validates the X-API-Key header.
    NGINX Ingress already blocks requests without the header;
    this layer validates the *value*.
    """
    if x_api_key not in _VALID_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Pass a valid X-API-Key header.",
        )
    return x_api_key


Auth = Annotated[str, Depends(require_api_key)]

# ── Response schemas ───────────────────────────────────────────────────────────

class DailySalesRow(BaseModel):
    order_date: date
    total_orders: int
    total_revenue: float
    avg_order_value: float


class TopProductRow(BaseModel):
    product_name: str
    category: str
    units_sold: int
    revenue: float


class RegionSummaryRow(BaseModel):
    region: str
    total_orders: int
    total_revenue: float
    unique_customers: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/sales/daily",
    response_model=list[DailySalesRow],
    summary="Daily sales summary",
    description="Aggregate daily orders & revenue. Query ClickHouse `orders` table.",
)
async def daily_sales(
    _key: Auth,
    days: Annotated[int, Query(ge=1, le=90, description="Number of past days")] = 30,
):
    sql = """
        SELECT
            toDate(order_ts)       AS order_date,
            count()                AS total_orders,
            sum(amount_usd)        AS total_revenue,
            avg(amount_usd)        AS avg_order_value
        FROM orders
        WHERE order_ts >= now() - INTERVAL {days:UInt32} DAY
        GROUP BY order_date
        ORDER BY order_date DESC
    """
    rows = await database.query(sql, {"days": days})
    return rows


@router.get(
    "/products/top",
    response_model=list[TopProductRow],
    summary="Top products by revenue",
)
async def top_products(
    _key: Auth,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
):
    sql = """
        SELECT
            product_name,
            category,
            sum(quantity)      AS units_sold,
            sum(amount_usd)    AS revenue
        FROM orders
        WHERE order_ts >= now() - INTERVAL {days:UInt32} DAY
        GROUP BY product_name, category
        ORDER BY revenue DESC
        LIMIT {limit:UInt32}
    """
    rows = await database.query(sql, {"days": days, "limit": limit})
    return rows


@router.get(
    "/regions/summary",
    response_model=list[RegionSummaryRow],
    summary="Sales summary by region",
)
async def region_summary(
    _key: Auth,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
):
    sql = """
        SELECT
            region,
            count()                   AS total_orders,
            sum(amount_usd)           AS total_revenue,
            uniq(customer_id)         AS unique_customers
        FROM orders
        WHERE order_ts >= now() - INTERVAL {days:UInt32} DAY
        GROUP BY region
        ORDER BY total_revenue DESC
    """
    rows = await database.query(sql, {"days": days})
    return rows

