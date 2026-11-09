"""
ClickHouse connection & query helpers.

Uses clickhouse-connect (HTTP driver — no native protocol needed).
Connection params are read from environment variables so they can be
injected as K8s Secrets without changing code.
"""

import os
import asyncio
from functools import lru_cache

import clickhouse_connect
from clickhouse_connect.driver.client import Client

# ── Config from environment (injected via K8s Secret / .env) ──────────────────
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")


@lru_cache(maxsize=1)
def get_client() -> Client:
    """
    Return a singleton ClickHouse client.
    lru_cache ensures we reuse the same connection pool.
    """
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DB,
        connect_timeout=10,
        send_receive_timeout=30,
    )


async def ping_clickhouse() -> None:
    """
    Async-friendly ping — runs the blocking ping() in a thread pool
    so it doesn't block the FastAPI event loop.
    Raises if ClickHouse is unreachable.
    """
    client = get_client()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, client.ping)


async def query(sql: str, parameters: dict | None = None) -> list[dict]:
    """
    Execute a SELECT query and return rows as a list of dicts.

    Args:
        sql: ClickHouse SQL string (use {param:Type} placeholders).
        parameters: Dict of named parameters for safe interpolation.

    Returns:
        List of row dicts with column names as keys.
    """
    client = get_client()
    loop = asyncio.get_event_loop()

    def _run():
        result = client.query(sql, parameters=parameters or {})
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    return await loop.run_in_executor(None, _run)

