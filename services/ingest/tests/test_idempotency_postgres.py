"""Real DB invariant test. Set DATABASE_URL to the migrated ingest database."""
import os, uuid
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

pytestmark=pytest.mark.skipif(not os.getenv("DATABASE_URL"),reason="DATABASE_URL is required for PostgreSQL integration tests")

@pytest.mark.asyncio
async def test_five_retries_create_one_event_and_outbox_row():
    engine=create_async_engine(os.environ["DATABASE_URL"]); Sessions=async_sessionmaker(engine,expire_on_commit=False)
    account,key_id=uuid.uuid4(),uuid.uuid4(); event=uuid.uuid4(); outbox_id=uuid.uuid4()
    try:
        async with Sessions() as db,db.begin():
            await db.execute(text("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES(:key,:account,:prefix,'test-hash')"),{"key":key_id,"account":account,"prefix":str(key_id)[:10]})
        for _ in range(5):
            async with Sessions() as db,db.begin():
                result=await db.execute(text("INSERT INTO usage_events(event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code) VALUES(:event,:account,:key,'/test',now(),1,200) ON CONFLICT(event_id) DO NOTHING"),{"event":event,"account":account,"key":key_id})
                if result.rowcount:
                    await db.execute(text("INSERT INTO outbox_messages(id,topic,payload) VALUES(:id,'usage.accepted','{}'::jsonb)"),{"id":outbox_id})
        async with Sessions() as db:
            assert await db.scalar(text("SELECT count(*) FROM usage_events WHERE event_id=:id"),{"id":event})==1
            assert await db.scalar(text("SELECT count(*) FROM outbox_messages WHERE id=:id AND topic='usage.accepted'"),{"id":outbox_id})==1
    finally:
        async with Sessions() as db,db.begin():
            await db.execute(text("DELETE FROM outbox_messages WHERE id=:id"),{"id":outbox_id})
            await db.execute(text("DELETE FROM usage_events WHERE event_id=:event"),{"event":event})
            await db.execute(text("DELETE FROM api_keys WHERE id=:key"),{"key":key_id})
        await engine.dispose()
