"""HTTP-level behaviour of POST /v1/usage that needs no database: auth, validation, 429 + Retry-After.

`authenticate` and the persistence layer are replaced by fakes, so these tests exercise the real
FastAPI wiring (headers, status codes, limiter) without PostgreSQL or RabbitMQ.
"""
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost/unused")
os.environ.setdefault("RABBITMQ_URL", "amqp://unused")
os.environ.setdefault("INTERNAL_TOKEN", "test-only-token")

from app import main as ingest_main  # noqa: E402
from app.ratelimit import FixedWindowLimiter  # noqa: E402

API_KEY = "k" * 32
ACCOUNT = uuid4()


class FakeSession:
    """Stands in for `Session()`: an async context manager whose `.begin()` is one too."""
    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return self


@pytest.fixture
def stored(monkeypatch):
    calls = []

    async def fake_authenticate(api_key):
        if api_key != API_KEY:
            raise HTTPException(401, "invalid API key")
        return SimpleNamespace(account_id=ACCOUNT, key_id=uuid4())

    async def fake_store_event(db, *, account_id, api_key_id, event):
        calls.append(event.event_id)
        return True

    monkeypatch.setattr(ingest_main, "authenticate", fake_authenticate)
    monkeypatch.setattr(ingest_main, "store_event", fake_store_event)
    monkeypatch.setattr(ingest_main, "Session", FakeSession())
    monkeypatch.setattr(ingest_main, "limiter", FixedWindowLimiter(2))
    return calls


def body(**overrides):
    payload = {"event_id": str(uuid4()), "endpoint": "/v1/test", "timestamp": datetime.now(timezone.utc).isoformat(),
               "duration_ms": 12, "status_code": 200}
    payload.update(overrides)
    return payload


async def post(payload, key=API_KEY):
    transport = httpx.ASGITransport(app=ingest_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest") as client:
        return await client.post("/v1/usage", json=payload, headers={"X-API-Key": key})


async def test_valid_event_is_accepted_with_202(stored):
    response = await post(body())
    assert response.status_code == 202
    assert len(stored) == 1


async def test_unknown_api_key_is_401_and_nothing_is_stored(stored):
    response = await post(body(), key="z" * 32)
    assert response.status_code == 401
    assert stored == []


async def test_invalid_payloads_are_422_and_nothing_is_stored(stored):
    assert (await post(body(status_code=999))).status_code == 422
    assert (await post(body(duration_ms=1.5))).status_code == 422
    assert (await post(body(unexpected="field"))).status_code == 422
    assert stored == []


async def test_exceeding_the_account_limit_returns_429_with_retry_after(stored):
    assert (await post(body())).status_code == 202
    assert (await post(body())).status_code == 202
    limited = await post(body())
    assert limited.status_code == 429
    retry_after = int(limited.headers["Retry-After"])
    assert 1 <= retry_after <= 60
    assert len(stored) == 2   # the throttled request never reached persistence
