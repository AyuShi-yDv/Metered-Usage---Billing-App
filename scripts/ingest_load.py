"""Measure POST /v1/usage latency against the local Compose stack.

The benchmark deliberately uses modest per-account concurrency so the measurement exercises
request latency rather than creating artificial lock contention in the rate limiter. The default
600 requests/minute limit is respected by the default 120 measured requests plus warm-up calls.
"""
import asyncio
import math
import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx

INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8000")
ADMIN_URL = os.getenv("INGEST_MANAGEMENT_URL", "http://localhost:8002")
INTERNAL_TOKEN = os.environ["INTERNAL_TOKEN"]
ACCOUNT_ID = UUID(os.getenv("LOAD_ACCOUNT_ID", "00000000-0000-0000-0000-000000000001"))
EVENTS = int(os.getenv("LOAD_EVENTS", "120"))
CONCURRENCY = int(os.getenv("LOAD_CONCURRENCY", "4"))
WARMUP = int(os.getenv("LOAD_WARMUP", "10"))


def percentile95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


async def main() -> None:
    if not 1 <= EVENTS <= 550 or CONCURRENCY < 1 or WARMUP < 0:
        raise ValueError("LOAD_EVENTS must be 1..550, LOAD_CONCURRENCY must be positive, LOAD_WARMUP must be >= 0")
    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    timeout = httpx.Timeout(5.0, connect=2.0)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        created = await client.post(
            f"{ADMIN_URL}/v1/api-keys", json={"account_id": str(ACCOUNT_ID)},
            headers={"X-Internal-Token": INTERNAL_TOKEN})
        created.raise_for_status()
        api_key = created.json()["secret"]

        async def send_one() -> tuple[int, float]:
            payload = {"event_id": str(uuid4()), "endpoint": "/load-test",
                       "timestamp": datetime.now(timezone.utc).isoformat(),
                       "duration_ms": 10, "status_code": 200}
            started = time.perf_counter()
            response = await client.post(f"{INGEST_URL}/v1/usage", json=payload,
                                         headers={"X-API-Key": api_key})
            return response.status_code, (time.perf_counter() - started) * 1000

        # Warm the HTTP connection, API-key cache and database connection pool before measuring.
        for _ in range(WARMUP):
            status, _ = await send_one()
            if status != 202:
                raise SystemExit(f"warm-up request failed with HTTP {status}")

        semaphore = asyncio.Semaphore(CONCURRENCY)
        async def measured() -> tuple[int, float]:
            async with semaphore:
                return await send_one()

        results = await asyncio.gather(*(measured() for _ in range(EVENTS)))

    statuses: dict[int, int] = {}
    latencies: list[float] = []
    for status, latency in results:
        statuses[status] = statuses.get(status, 0) + 1
        latencies.append(latency)

    ordered = sorted(latencies)
    p50 = ordered[len(ordered) // 2]
    p95 = percentile95(ordered)
    print(f"events={EVENTS} warmup={WARMUP} concurrency={CONCURRENCY} statuses={statuses}")
    print(f"latency_ms p50={p50:.2f} p95={p95:.2f} max={ordered[-1]:.2f}")
    if statuses != {202: EVENTS} or p95 >= 50:
        raise SystemExit("ingest p95 target failed (required: all accepted and p95 < 50 ms)")
    print("PASS: ingest p95 < 50 ms")


if __name__ == "__main__":
    asyncio.run(main())
