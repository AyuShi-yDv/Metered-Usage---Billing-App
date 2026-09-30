"""Duplicate deliveries from the broker must count exactly once (needs DATABASE_URL)."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.consumer import apply_usage_event


def parsed(account, event, status=200):
    return {"event": event, "account": account, "endpoint": "/v1/x", "occurred": datetime.now(timezone.utc),
            "duration": 5, "status": status}


async def test_same_event_delivered_five_times_is_one_billable_event(sessions, make_tenant):
    t = await make_tenant(); event = uuid.uuid4(); results = []
    for _ in range(5):
        async with sessions() as db, db.begin():
            results.append(await apply_usage_event(db, parsed(t.account, event)))
    assert results == [True, False, False, False, False]
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM billing_events WHERE event_id=:e"), {"e": event}) == 1
        assert await db.scalar(text("SELECT count(*) FROM rollup_tasks WHERE account_id=:a"), {"a": t.account}) == 1


async def test_concurrent_redelivery_is_still_counted_once(sessions, make_tenant):
    t = await make_tenant(); event = uuid.uuid4()

    async def deliver():
        async with sessions() as db, db.begin():
            return await apply_usage_event(db, parsed(t.account, event))

    assert sum(await asyncio.gather(*(deliver() for _ in range(5)))) == 1


async def test_unknown_account_is_created_on_the_starter_plan(sessions):
    account = uuid.uuid4()
    try:
        async with sessions() as db, db.begin():   # same fixed row the billing service bootstraps (idempotent)
            await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) "
                                  "VALUES('00000000-0000-0000-0000-000000000010','Starter',10000,250,1900) ON CONFLICT DO NOTHING"))
            assert await apply_usage_event(db, parsed(account, uuid.uuid4()))
        async with sessions() as db:
            plan = await db.scalar(text("SELECT p.name FROM account_plans ap JOIN plans p ON p.id=ap.plan_id WHERE ap.account_id=:a"), {"a": account})
        assert plan == "Starter"
    finally:
        async with sessions() as db, db.begin():
            for sql in ("DELETE FROM rollup_tasks WHERE account_id=:a", "DELETE FROM billing_events WHERE account_id=:a",
                        "DELETE FROM account_plans WHERE account_id=:a", "DELETE FROM accounts WHERE id=:a"):
                await db.execute(text(sql), {"a": account})
