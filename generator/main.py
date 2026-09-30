"""Usage-event generator.

Replays events at EVENTS_PER_SECOND and deliberately misbehaves like a real at-least-once client:
  * DUPLICATE_RATE of events are delivered again 1-4 more times (so up to 5 deliveries of one event_id),
    the extra copies scheduled 0-30 s later, i.e. out of order relative to newer events;
  * LATE_RATE of events carry a timestamp up to 23.5 h in the past (accepted window is 24 h).
"""
import asyncio
import heapq
import itertools
import os
import random
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx

INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8000")
INGEST_MANAGEMENT_URL = os.getenv("INGEST_MANAGEMENT_URL", INGEST_URL)
RATE = float(os.getenv("EVENTS_PER_SECOND", "4"))
DUPLICATE_RATE = float(os.getenv("DUPLICATE_RATE", "0.10"))
LATE_RATE = float(os.getenv("LATE_RATE", "0.15"))
TOKEN = os.getenv("INTERNAL_TOKEN", "change-me-in-production")
ACCOUNT = UUID(os.getenv("GENERATOR_ACCOUNT_ID", "00000000-0000-0000-0000-000000000001"))
ENDPOINTS = ["/v1/search", "/v1/files", "/v1/export", "/v1/users"]
if RATE <= 0:
    raise ValueError("EVENTS_PER_SECOND must be positive")


async def get_key(client: httpx.AsyncClient) -> str:
    backoff = 1.0
    while True:
        try:
            response = await client.post(f"{INGEST_MANAGEMENT_URL}/v1/api-keys", json={"account_id": str(ACCOUNT)}, headers={"X-Internal-Token": TOKEN})
            response.raise_for_status()
            return response.json()["secret"]
        except httpx.HTTPError:
            await asyncio.sleep(backoff * random.uniform(0.75, 1.25))
            backoff = min(backoff * 2, 30.0)


def new_event() -> dict:
    late = timedelta(hours=random.uniform(0, 23.5)) if random.random() < LATE_RATE else timedelta()
    return {
        "event_id": str(uuid4()),
        "endpoint": random.choice(ENDPOINTS),
        "timestamp": (datetime.now(timezone.utc) - late).isoformat(),
        "duration_ms": random.randint(5, 1200),
        "status_code": random.choices([200, 201, 400, 404, 500], [65, 5, 12, 8, 10])[0],
    }


async def main() -> None:
    async with httpx.AsyncClient(timeout=2) as client:
        key = await get_key(client)
        pending: list[tuple[float, int, dict]] = []   # (send_at, tiebreak, payload): delayed duplicate deliveries
        counter = itertools.count()

        async def send(payload: dict) -> None:
            nonlocal key
            try:
                response = await client.post(f"{INGEST_URL}/v1/usage", json=payload, headers={"X-API-Key": key})
            except httpx.HTTPError:
                return  # ingest down: drop this delivery, keep generating
            if response.status_code == 429:
                await asyncio.sleep(min(float(response.headers.get("Retry-After", "1")), 5.0))
            elif response.status_code == 401:
                key = await get_key(client)

        while True:
            now = time.monotonic()
            while pending and pending[0][0] <= now:
                await send(heapq.heappop(pending)[2])
            event = new_event()
            await send(event)
            if random.random() < DUPLICATE_RATE:
                for _ in range(random.choice([1, 1, 2, 4])):
                    heapq.heappush(pending, (now + random.uniform(0, 30), next(counter), event))
            await asyncio.sleep(1 / RATE)


if __name__ == "__main__":
    asyncio.run(main())
