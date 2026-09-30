"""Idempotent ingest, exercised through the real `store_event` (needs DATABASE_URL, migrated ingest DB)."""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration tests")
os.environ.setdefault("RABBITMQ_URL", "amqp://unused")
os.environ.setdefault("INTERNAL_TOKEN", "integration-test")


def make_event(event_id):
    from app.schemas import UsageIn
    return UsageIn(event_id=event_id, endpoint="/v1/test", timestamp=datetime.now(timezone.utc), duration_ms=5, status_code=200)


@pytest.fixture
async def sessions():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def key(sessions):
    account, key_id = uuid.uuid4(), uuid.uuid4()
    async with sessions() as db, db.begin():
        await db.execute(text("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES(:k,:a,:p,'x')"),
                         {"k": key_id, "a": account, "p": key_id.hex[:10]})
    yield account, key_id
    async with sessions() as db, db.begin():
        await db.execute(text("DELETE FROM outbox_messages WHERE payload->>'account_id'=:a"), {"a": str(account)})
        await db.execute(text("DELETE FROM usage_events WHERE account_id=:a"), {"a": account})
        await db.execute(text("DELETE FROM api_keys WHERE id=:k"), {"k": key_id})


async def test_same_event_five_times_yields_one_event_and_one_outbox_row(sessions, key):
    from app.repository import store_event
    account, key_id = key
    event = make_event(uuid.uuid4())
    results = []
    for _ in range(5):
        async with sessions() as db, db.begin():
            results.append(await store_event(db, account_id=account, api_key_id=key_id, event=event))
    assert results == [True, False, False, False, False]
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM usage_events WHERE event_id=:e"), {"e": event.event_id}) == 1
        assert await db.scalar(text("SELECT count(*) FROM outbox_messages WHERE payload->>'event_id'=:e"), {"e": str(event.event_id)}) == 1


async def test_five_concurrent_deliveries_of_the_same_event_yield_one_row(sessions, key):
    from app.repository import store_event
    account, key_id = key
    event = make_event(uuid.uuid4())

    async def deliver():
        async with sessions() as db, db.begin():
            return await store_event(db, account_id=account, api_key_id=key_id, event=event)

    results = await asyncio.gather(*(deliver() for _ in range(5)))
    assert sum(results) == 1
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM outbox_messages WHERE payload->>'event_id'=:e"), {"e": str(event.event_id)}) == 1
