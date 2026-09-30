"""Measure POST /v1/usage latency against the local Compose stack."""
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
EVENTS = int(os.getenv("LOAD_EVENTS", "100"))
CONCURRENCY = int(os.getenv("LOAD_CONCURRENCY", "2"))


def percentile95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


async def main() -> None:
    if not 1 <= EVENTS <= 550 or CONCURRENCY < 1:
        raise ValueError("LOAD_EVENTS must be 1..550 and LOAD_CONCURRENCY must be positive")
    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    async with httpx.AsyncClient(timeout=5, limits=limits) as client:
        created = await client.post(f"{ADMIN_URL}/v1/api-keys", json={"account_id": str(ACCOUNT_ID)},
            headers={"X-Internal-Token": INTERNAL_TOKEN})
        created.raise_for_status()
        api_key = created.json()["secret"]
        now = datetime.now(timezone.utc).isoformat()
        semaphore = asyncio.Semaphore(CONCURRENCY)
        latencies: list[float] = []
        statuses: dict[int, int] = {}
        latencies_by_status: dict[int, list[float]] = {}

        async def send_one() -> None:
            async with semaphore:
                payload = {"event_id": str(uuid4()), "endpoint": "/load-test",
                    "timestamp": now, "duration_ms": 10, "status_code": 200}
                started = time.perf_counter()
                response = await client.post(f"{INGEST_URL}/v1/usage", json=payload,
                    headers={"X-API-Key": api_key})
                latency_ms = (time.perf_counter() - started) * 1000
                latencies.append(latency_ms)
                latencies_by_status.setdefault(response.status_code, []).append(latency_ms)
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1

        await asyncio.gather(*(send_one() for _ in range(EVENTS)))

    ordered = sorted(latencies)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    print(f"events={EVENTS} concurrency={CONCURRENCY} statuses={statuses}")
    print(f"latency_ms p50={ordered[len(ordered)//2]:.2f} p95={p95:.2f} max={ordered[-1]:.2f}")
    for code, samples in sorted(latencies_by_status.items()):
        samples.sort()
        status_p95 = samples[max(0, math.ceil(0.95 * len(samples)) - 1)]
        print(f"latency_ms status={code} count={len(samples)} p50={samples[len(samples)//2]:.2f} p95={status_p95:.2f} max={samples[-1]:.2f}")
    if statuses != {202: EVENTS} or p95 >= 50:
        raise SystemExit("ingest p95 target failed (required: all accepted and p95 < 50 ms)")


if __name__ == "__main__":
    asyncio.run(main())
