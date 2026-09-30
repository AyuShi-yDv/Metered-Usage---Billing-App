"""Invoice totals, proration, exactly-once finalize and late-arrival handling (needs DATABASE_URL)."""
import asyncio
import uuid
from datetime import datetime, timedelta

from conftest import UTC, add_events
from sqlalchemy import text

from app import invoices as service
from app.charges import PERIOD_CHARGES_SQL
from app.worker import process_one_rollup


async def finalize(sessions, account, period):
    async with sessions() as db, db.begin():
        return await service.finalize(db, account, period)


async def test_invoice_is_base_fee_plus_overage_rounded_once(sessions, make_tenant):
    t = await make_tenant(included=1000, per_1000=500, base=1000)   # $10.00 base, 1000 included, $5.00 / 1000 over
    jan = datetime(2024, 1, 1, tzinfo=UTC)
    await add_events(sessions, t.account, [(jan + timedelta(minutes=i), "/a", 1, 200) for i in range(1500)] + [(jan, "/a", 1, 500)] * 50)
    async with sessions() as db:
        charge = (await db.execute(PERIOD_CHARGES_SQL, {"account": t.account, "start": jan, "end": datetime(2024, 2, 1, tzinfo=UTC)})).mappings().one()
    assert (charge["calls"], charge["base_fee_cents"], charge["overage_cents"], charge["total_cents"]) == (1500, 1000, 250, 1250)


async def test_redirects_and_server_errors_are_not_invoiced(sessions, make_tenant):
    t = await make_tenant(included=1000, per_1000=500, base=1000)
    jan = datetime(2024, 1, 1, tzinfo=UTC)
    await add_events(sessions, t.account,
                     [(jan + timedelta(minutes=i), "/a", 1, 200) for i in range(1000)]
                     + [(jan, "/a", 1, 302)] * 400 + [(jan, "/a", 1, 500)] * 400 + [(jan, "/a", 1, 404)] * 500)
    async with sessions() as db:
        charge = (await db.execute(PERIOD_CHARGES_SQL, {"account": t.account, "start": jan, "end": datetime(2024, 2, 1, tzinfo=UTC)})).mappings().one()
    # 1000 x 200 + 500 x 404 = 1500 billable; 500 over the allowance at 500c/1000 = 250c
    assert (charge["calls"], charge["overage_cents"], charge["total_cents"]) == (1500, 250, 1250)


async def test_finalize_twice_concurrently_creates_one_invoice_whose_lines_sum_to_the_total(sessions, make_tenant):
    t = await make_tenant(included=1000, per_1000=500, base=1000)
    jan = datetime(2024, 1, 1, tzinfo=UTC)
    await add_events(sessions, t.account, [(jan + timedelta(minutes=i), "/a", 1, 200) for i in range(1500)])
    results = await asyncio.gather(finalize(sessions, t.account, jan), finalize(sessions, t.account, jan))
    assert sorted(r["created"] for r in results) == [False, True]
    assert results[0]["invoice_id"] == results[1]["invoice_id"]
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM invoices WHERE account_id=:a"), {"a": t.account}) == 1
        total = await db.scalar(text("SELECT total_cents FROM invoices WHERE account_id=:a"), {"a": t.account})
        lines = await db.scalar(text("SELECT sum(l.amount_cents) FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id WHERE i.account_id=:a"), {"a": t.account})
    assert total == lines == 1250


async def test_open_period_cannot_be_finalized(sessions, make_tenant):
    import pytest
    from fastapi import HTTPException
    t = await make_tenant()
    with pytest.raises(HTTPException) as err:
        await finalize(sessions, t.account, datetime.now(UTC))
    assert err.value.status_code == 409


async def test_event_after_final_invoice_becomes_a_next_invoice_adjustment(sessions, make_tenant):
    t = await make_tenant(included=0, per_1000=500, base=0)
    dec = datetime(2023, 12, 1, tzinfo=UTC)
    await finalize(sessions, t.account, dec)                                   # issued with zero usage
    await add_events(sessions, t.account, [(dec + timedelta(hours=2), "/late", 12, 200)])
    async with sessions() as db, db.begin():
        await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:a,:h)"), {"a": t.account, "h": dec + timedelta(hours=2)})
    while await process_one_rollup():
        pass
    async with sessions() as db:
        adjustment = await db.scalar(text("SELECT sum(amount_cents) FROM late_adjustments WHERE account_id=:a AND source_period_start=:m"), {"a": t.account, "m": dec})
        invoiced = await db.scalar(text("SELECT total_cents FROM invoices WHERE account_id=:a"), {"a": t.account})
    assert adjustment == 1 and invoiced == 0          # 0.5 cent rounds up once; the issued invoice is untouched
    await finalize(sessions, t.account, datetime(2024, 1, 1, tzinfo=UTC))      # next invoice picks it up exactly once
    async with sessions() as db:
        applied = await db.scalar(text("SELECT count(*) FROM late_adjustments WHERE account_id=:a AND applied_invoice_id IS NOT NULL"), {"a": t.account})
    assert applied == 1


async def test_mid_month_plan_change_prorates_allowance_and_base_fee(sessions, make_tenant):
    t = await make_tenant(included=200, per_1000=500, base=1000)
    plan_b = uuid.uuid4()
    start, mid, end = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 16, tzinfo=UTC), datetime(2024, 1, 31, tzinfo=UTC)
    try:
        async with sessions() as db, db.begin():
            await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:b,:n,300,1000,2000)"), {"b": plan_b, "n": f"test-{plan_b}"})
            await db.execute(text("UPDATE account_plans SET effective_to=:mid WHERE account_id=:a"), {"mid": mid, "a": t.account})
            await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(gen_random_uuid(),:a,:b,:mid)"), {"a": t.account, "b": plan_b, "mid": mid})
        await add_events(sessions, t.account, [(start + timedelta(seconds=i), "/p", 1, 200) for i in range(1, 151)])
        await add_events(sessions, t.account, [(mid + timedelta(seconds=i), "/p", 1, 200) for i in range(1, 301)])
        async with sessions() as db:
            charge = (await db.execute(PERIOD_CHARGES_SQL, {"account": t.account, "start": start, "end": end})).mappings().one()
        assert (charge["calls"], charge["base_fee_cents"], charge["overage_cents"]) == (450, 1500, 175)
    finally:
        async with sessions() as db, db.begin():   # make_tenant removes plan A; plan B is ours
            await db.execute(text("DELETE FROM account_plans WHERE plan_id=:b"), {"b": plan_b})
            await db.execute(text("DELETE FROM plans WHERE id=:b"), {"b": plan_b})
