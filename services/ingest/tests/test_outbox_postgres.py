"""Two publishers must never claim the same outbox row (needs DATABASE_URL, migrated ingest DB)."""
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL is required for PostgreSQL integration tests")
os.environ.setdefault("RABBITMQ_URL", "amqp://unused")
os.environ.setdefault("INTERNAL_TOKEN", "integration-test")


async def test_concurrent_claims_are_disjoint():
    from app.outbox import CLAIM_SQL
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Sessions = async_sessionmaker(engine, expire_on_commit=False)
    marker = str(uuid.uuid4())
    ids = [uuid.uuid4() for _ in range(6)]
    try:
        async with Sessions() as db, db.begin():
            for i in ids:
                await db.execute(text("INSERT INTO outbox_messages(id,topic,payload) VALUES(:i,'usage.accepted',CAST(:p AS jsonb))"),
                                 {"i": i, "p": f'{{"marker":"{marker}"}}'})
        # Hold worker A's row locks open, then let worker B claim: B must get only unlocked rows.
        async with Sessions() as a, a.begin():
            first = {r["id"] for r in (await a.execute(CLAIM_SQL, {"limit": 3})).mappings().all()}
            async with Sessions() as b, b.begin():
                second = {r["id"] for r in (await b.execute(CLAIM_SQL, {"limit": 100})).mappings().all()}
        assert first, "worker A should have claimed rows"
        assert not (first & second), "a row was claimed by both publishers"
    finally:
        async with Sessions() as db, db.begin():
            await db.execute(text("DELETE FROM outbox_messages WHERE payload->>'marker'=:m"), {"m": marker})
        await engine.dispose()
