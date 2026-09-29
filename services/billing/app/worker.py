from datetime import timedelta
from .db import Session
from .charges import PERIOD_CHARGES_SQL
from sqlalchemy import text

async def process_one_rollup() -> bool:
    async with Session() as db, db.begin():
        task = (await db.execute(text("SELECT account_id,hour_start FROM rollup_tasks ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"))).mappings().first()
        if not task: return False
        end = task["hour_start"] + timedelta(hours=1)
        month_start = task["hour_start"].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        lock_scope=f"{task['account_id']}:{month_start.isoformat()}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),{"scope":lock_scope})
        await db.execute(text("DELETE FROM hourly_usage_rollups WHERE account_id=:account AND hour_start=:hour"), {"account":task["account_id"],"hour":task["hour_start"]})
        await db.execute(text("""INSERT INTO hourly_usage_rollups(account_id,hour_start,endpoint,billable_calls,total_calls)
        SELECT account_id,date_trunc('hour',occurred_at),endpoint,
        count(*) FILTER (WHERE status_code BETWEEN 200 AND 499),count(*) FROM billing_events
        WHERE account_id=:account AND occurred_at>=:hour AND occurred_at<:end GROUP BY account_id,date_trunc('hour',occurred_at),endpoint"""), {"account":task["account_id"],"hour":task["hour_start"],"end":end})
        await db.execute(text("DELETE FROM rollup_tasks WHERE account_id=:account AND hour_start=:hour"), {"account":task["account_id"],"hour":task["hour_start"]})
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        finalized = (await db.execute(text("SELECT id,overage_cents FROM invoices WHERE account_id=:account AND period_start=:month AND status='final'"), {"account":task["account_id"],"month":month_start})).mappings().first()
        if finalized:
            period_charges = (await db.execute(PERIOD_CHARGES_SQL, {"account":task["account_id"],"start":month_start,"end":month_end})).mappings().first()
            existing_delta = (await db.execute(text("SELECT COALESCE(sum(amount_cents),0) FROM late_adjustments WHERE account_id=:account AND source_period_start=:month"), {"account":task["account_id"],"month":month_start})).scalar_one()
            # Invoices are immutable; late arrivals create only the additional
            # period charge not already represented by the original invoice or
            # earlier adjustment rows.
            desired = max(0,period_charges["overage_cents"]-finalized["overage_cents"])
            if desired > existing_delta:
                await db.execute(text("INSERT INTO late_adjustments(id,account_id,source_period_start,amount_cents) VALUES(gen_random_uuid(),:account,:month,:amount)"), {"account":task["account_id"],"month":month_start,"amount":desired-existing_delta})
    return True
