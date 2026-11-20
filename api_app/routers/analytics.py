"""
Analytics router — all business endpoints live here.

Sử dụng AnalyticsAuth: Tự động thẩm định Timestamp + SHA256(key + timestamp)
đối chiếu với danh sách ANALYTICS_API_KEYS của service Analytics.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api_app import database
from api_app.auth import AnalyticsAuth

router = APIRouter()

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
    _client: AnalyticsAuth,
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
    _client: AnalyticsAuth,
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
    _client: AnalyticsAuth,
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
