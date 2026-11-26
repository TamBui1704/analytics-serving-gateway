"""
ClickHouse connection & query helpers (Thread-Safe).

Uses clickhouse-connect (HTTP driver — no native protocol needed).
Connection params are read from environment variables so they can be
injected as K8s Secrets / .env without changing code.

Thread-safety note:
  clickhouse_connect.Client is NOT thread-safe for concurrent queries on a single
  instance. We use threading.local() so each worker thread in asyncio's executor
  gets its own Client instance while sharing a thread-safe urllib3 PoolManager.
"""

import asyncio
import os
import threading

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from clickhouse_connect.driver.httputil import get_pool_manager

# ── Config from environment (injected via K8s Secret / .env) ──────────────────
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "analytics")

# Shared thread-safe HTTP connection pool across executor threads
_POOL_MANAGER = get_pool_manager(maxsize=16, num_pools=4)
_THREAD_LOCAL = threading.local()


def get_client() -> Client:
    """
    Return a thread-local ClickHouse client backed by a shared HTTP PoolManager.
    Safe for concurrent asyncio run_in_executor calls.
    """
    client: Client | None = getattr(_THREAD_LOCAL, "client", None)
    if client is None:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DB,
            connect_timeout=10,
            send_receive_timeout=30,
            pool_mgr=_POOL_MANAGER,
        )
        _THREAD_LOCAL.client = client
    return client


async def ping_clickhouse() -> None:
    """
    Async-friendly ping — runs the blocking ping() in a thread pool
    so it doesn't block the FastAPI event loop.
    Raises if ClickHouse is unreachable.
    """
    loop = asyncio.get_running_loop()

    def _ping():
        get_client().ping()

    await loop.run_in_executor(None, _ping)


async def query(sql: str, parameters: dict | None = None) -> list[dict]:
    """
    Execute a SELECT query and return rows as a list of dicts.

    Args:
        sql: ClickHouse SQL string (use {param:Type} placeholders).
        parameters: Dict of named parameters for safe interpolation.

    Returns:
        List of row dicts with column names as keys.
    """
    loop = asyncio.get_running_loop()

    def _run():
        client = get_client()
        result = client.query(sql, parameters=parameters or {})
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    return await loop.run_in_executor(None, _run)
