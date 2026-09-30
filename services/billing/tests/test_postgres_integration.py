"""Real PostgreSQL checks. Set DATABASE_URL to migrated billing DB to enable."""
import asyncio, os, uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

pytestmark=pytest.mark.skipif(not os.getenv("DATABASE_URL"),reason="DATABASE_URL is required for real PostgreSQL integration tests")
os.environ.setdefault("RABBITMQ_URL","amqp://unused")
os.environ.setdefault("INTERNAL_TOKEN","integration-test")

@pytest.mark.asyncio
async def test_two_workers_do_not_double_count_and_5xx_is_excluded():
    engine=create_async_engine(os.environ["DATABASE_URL"])
    Sessions=async_sessionmaker(engine,expire_on_commit=False)
    account=uuid.uuid4(); hour=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
    try:
        async with Sessions() as db, db.begin():
            await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'concurrency-test')"),{"id":account})
            await db.execute(text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) VALUES(:id,:account,'/test',:hour,30,200),(:id2,:account,'/test',:hour,30,503)"),{"id":uuid.uuid4(),"id2":uuid.uuid4(),"account":account,"hour":hour})
            await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:account,:hour)"),{"account":account,"hour":hour})
        from app.worker import process_one_rollup
        assert sum(await asyncio.gather(process_one_rollup(),process_one_rollup()))==1
        async with Sessions() as db:
            row=(await db.execute(text("SELECT billable_calls,total_calls FROM hourly_usage_rollups WHERE account_id=:account"),{"account":account})).one()
            assert row.billable_calls==1 and row.total_calls==2
        duplicate=uuid.uuid4()
        async with Sessions() as db, db.begin():
            inserted=0
            for _ in range(5):
                result=await db.execute(text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) VALUES(:id,:account,'/duplicate',:hour,1,200) ON CONFLICT(event_id) DO NOTHING"),{"id":duplicate,"account":account,"hour":hour})
                inserted+=result.rowcount
            assert inserted==1
    finally:
        async with Sessions() as db, db.begin():
            await db.execute(text("DELETE FROM hourly_usage_rollups WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM billing_events WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM accounts WHERE id=:account"),{"account":account})
        await engine.dispose()
        # The rollup worker uses app.db's module-level engine. Dispose it so
        # asyncpg connections are not reused by pytest's next event loop.
        from app.db import engine as worker_engine
        await worker_engine.dispose()

@pytest.mark.asyncio
async def test_event_after_final_invoice_becomes_next_period_adjustment():
    from datetime import timedelta
    from app.worker import process_one_rollup
    engine=create_async_engine(os.environ["DATABASE_URL"]); Sessions=async_sessionmaker(engine,expire_on_commit=False)
    account,plan,invoice,event=uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    current_month=datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    source_month=(current_month.replace(day=1)-timedelta(days=1)).replace(day=1)
    source_end=current_month; hour=source_month+timedelta(hours=2)
    try:
        async with Sessions() as db,db.begin():
            await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'late-event-test')"),{"id":account})
            await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:id,:name,0,500,0)"),{"id":plan,"name":f"late-{plan}"})
            await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(:id,:account,:plan,:from)"),{"id":uuid.uuid4(),"account":account,"plan":plan,"from":datetime(2020,1,1,tzinfo=timezone.utc)})
            await db.execute(text("INSERT INTO invoices(id,account_id,period_start,period_end,status,base_fee_cents,overage_cents,total_cents) VALUES(:id,:account,:start,:end,'final',0,0,0)"),{"id":invoice,"account":account,"start":source_month,"end":source_end})
            await db.execute(text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) VALUES(:event,:account,'/late',:hour,12,200)"),{"event":event,"account":account,"hour":hour})
            await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:account,:hour)"),{"account":account,"hour":hour})
        assert await process_one_rollup()
        async with Sessions() as db:
            adjustment=await db.scalar(text("SELECT amount_cents FROM late_adjustments WHERE account_id=:account AND source_period_start=:month"),{"account":account,"month":source_month})
            assert adjustment==1
    finally:
        async with Sessions() as db,db.begin():
            await db.execute(text("DELETE FROM late_adjustments WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM invoice_lines WHERE invoice_id=:invoice"),{"invoice":invoice})
            await db.execute(text("DELETE FROM invoices WHERE id=:invoice"),{"invoice":invoice})
            await db.execute(text("DELETE FROM hourly_usage_rollups WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM rollup_tasks WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM billing_events WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM account_plans WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM accounts WHERE id=:account"),{"account":account})
            await db.execute(text("DELETE FROM plans WHERE id=:plan"),{"plan":plan})
        await engine.dispose()

@pytest.mark.asyncio
async def test_mid_month_plan_change_prorates_allowance_and_base_fee():
    from app.charges import PERIOD_CHARGES_SQL
    engine=create_async_engine(os.environ["DATABASE_URL"]); Sessions=async_sessionmaker(engine,expire_on_commit=False)
    account,plan_a,plan_b=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    start=datetime(2024,1,1,tzinfo=timezone.utc); midpoint=datetime(2024,1,16,tzinfo=timezone.utc); end=datetime(2024,1,31,tzinfo=timezone.utc)
    try:
        async with Sessions() as db,db.begin():
            await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'proration-test')"),{"id":account})
            await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:a,:an,200,500,1000),(:b,:bn,300,1000,2000)"),{"a":plan_a,"an":f"prorate-a-{plan_a}","b":plan_b,"bn":f"prorate-b-{plan_b}"})
            await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from,effective_to) VALUES(:id,:account,:a,:start,:mid),(:id2,:account,:b,:mid,NULL)"),{"id":uuid.uuid4(),"id2":uuid.uuid4(),"account":account,"a":plan_a,"b":plan_b,"start":start,"mid":midpoint})
            await db.execute(text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) SELECT gen_random_uuid(),:account,'/proration',CAST(:start AS timestamptz)+gs.n*interval '1 second',1,200 FROM generate_series(1,150) AS gs(n)"),{"account":account,"start":start})
            await db.execute(text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) SELECT gen_random_uuid(),:account,'/proration',CAST(:mid AS timestamptz)+gs.n*interval '1 second',1,200 FROM generate_series(1,300) AS gs(n)"),{"account":account,"mid":midpoint})
        async with Sessions() as db:
            charge=(await db.execute(PERIOD_CHARGES_SQL,{"account":account,"start":start,"end":end})).mappings().one()
            assert charge["calls"]==450
            assert charge["base_fee_cents"]==1500
            assert charge["overage_cents"]==175
    finally:
        async with Sessions() as db,db.begin():
            await db.execute(text("DELETE FROM billing_events WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM account_plans WHERE account_id=:account"),{"account":account})
            await db.execute(text("DELETE FROM accounts WHERE id=:account"),{"account":account})
            await db.execute(text("DELETE FROM plans WHERE id IN (:a,:b)"),{"a":plan_a,"b":plan_b})
        await engine.dispose()
