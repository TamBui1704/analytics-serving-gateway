-- ============================================================
-- ClickHouse Init Script — Analytics Database
-- Executed automatically on first docker-compose up
-- ============================================================

CREATE DATABASE IF NOT EXISTS analytics;

-- ── Orders table (MergeTree — ClickHouse's core OLAP engine) ─────────────────
CREATE TABLE IF NOT EXISTS analytics.orders
(
    order_id       UUID         DEFAULT generateUUIDv4(),
    order_ts       DateTime,
    customer_id    UInt32,
    product_name   String,
    category       LowCardinality(String),
    region         LowCardinality(String),
    quantity       UInt16,
    amount_usd     Float64,
    status         LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(order_ts)
ORDER BY (order_ts, customer_id)
SETTINGS index_granularity = 8192;

-- ── Seed sample data — 90 days of synthetic orders ───────────────────────────
INSERT INTO analytics.orders
    (order_ts, customer_id, product_name, category, region, quantity, amount_usd, status)
SELECT
    now() - toIntervalDay(rand() % 90) - toIntervalSecond(rand() % 86400),
    rand() % 10000 + 1,
    ['Laptop Pro', 'Wireless Mouse', 'USB-C Hub', 'Keyboard MX',
     'Monitor 4K', 'Webcam HD', 'SSD 1TB', 'RAM 16GB',
     'Standing Desk', 'Ergonomic Chair'][rand() % 10 + 1],
    ['Electronics', 'Accessories', 'Furniture'][rand() % 3 + 1],
    ['North America', 'Europe', 'Asia Pacific', 'Latin America'][rand() % 4 + 1],
    rand() % 5 + 1,
    round((rand() % 2000 + 20) * (1 + rand() % 100 / 100.0), 2),
    ['completed', 'completed', 'completed', 'pending', 'cancelled'][rand() % 5 + 1]
FROM numbers(50000);  -- Insert 50,000 rows

-- ── Verify ───────────────────────────────────────────────────────────────────
SELECT
    'Seed complete' AS msg,
    count()         AS total_rows,
    min(order_ts)   AS earliest,
    max(order_ts)   AS latest
FROM analytics.orders;

