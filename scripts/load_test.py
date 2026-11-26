#!/usr/bin/env python3
"""
Lightweight concurrent Load Test for Analytics Serving Gateway (stdlib only).

Kiểm chứng:
  1. Thread-safety của ClickHouse client dưới tải đồng thời (không lỗi concurrent session).
  2. Xác thực HMAC-SHA256 hợp lệ trên toàn bộ request.
  3. Đo độ trễ p50 / p95 / max và tỉ lệ thành công.

Cách chạy:
  python3 scripts/load_test.py --url http://127.0.0.1:8000/api/v1/sales/daily?days=7 --requests 30 --concurrency 10
"""

import argparse
import concurrent.futures
import hashlib
import hmac
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def make_hmac_headers(secret_key: str, method: str, path: str) -> dict[str, str]:
    now = str(int(time.time()))
    canonical = f"{method.upper()}:{path}:{now}".encode("utf-8")
    sig = hmac.new(secret_key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return {"Timestamp": now, "Authorization": f"Bearer {sig}"}


def send_one(url: str, secret_key: str) -> tuple[int, float, str]:
    parsed = urllib.parse.urlparse(url)
    headers = make_hmac_headers(secret_key, "GET", parsed.path)
    req = urllib.request.Request(url, headers=headers, method="GET")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
            return resp.status, (time.perf_counter() - start) * 1000, ""
    except urllib.error.HTTPError as exc:
        return exc.code, (time.perf_counter() - start) * 1000, str(exc)
    except Exception as exc:
        return 0, (time.perf_counter() - start) * 1000, str(exc)


def main():
    parser = argparse.ArgumentParser(description="Concurrent load test for Analytics Serving Gateway")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/sales/daily?days=7")
    parser.add_argument("--key", default="key_user_a")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    print(f"Running {args.requests} requests (concurrency={args.concurrency}) -> {args.url}")
    t0 = time.perf_counter()
    statuses: dict[int, int] = {}
    latencies: list[float] = []
    errors: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(send_one, args.url, args.key) for _ in range(args.requests)]
        for fut in concurrent.futures.as_completed(futures):
            code, ms, err = fut.result()
            statuses[code] = statuses.get(code, 0) + 1
            latencies.append(ms)
            if err:
                errors.append(f"[{code}] {err}")

    total_s = time.perf_counter() - t0
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    print(f"\nDone in {total_s:.2f}s ({args.requests / total_s:.1f} req/s)")
    print(f"Status codes : {statuses}")
    print(f"Latency (ms) : min={latencies[0]:.1f} | p50={p50:.1f} | p95={p95:.1f} | max={latencies[-1]:.1f}")
    if errors:
        print(f"Sample errors ({len(errors)} total): {errors[:3]}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

