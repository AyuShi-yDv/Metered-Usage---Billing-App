from datetime import timedelta
from sqlalchemy import text
from .db import Session

async def process_one_rollup() -> bool:
    async with Session() as db, db.begin():
        task = (await db.execute(text("SELECT account_id,hour_start FROM rollup_tasks ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"))).mappings().first()
        if not task: return False
        end = task["hour_start"] + timedelta(hours=1)
        await db.execute(text("DELETE FROM hourly_usage_rollups WHERE account_id=:account AND hour_start=:hour"), {"account":task["account_id"],"hour":task["hour_start"]})
        await db.execute(text("""INSERT INTO hourly_usage_rollups(account_id,hour_start,endpoint,billable_calls,total_calls)
        SELECT account_id,date_trunc('hour',occurred_at),endpoint,
        count(*) FILTER (WHERE status_code BETWEEN 200 AND 499),count(*) FROM billing_events
        WHERE account_id=:account AND occurred_at>=:hour AND occurred_at<:end GROUP BY account_id,date_trunc('hour',occurred_at),endpoint"""), {"account":task["account_id"],"hour":task["hour_start"],"end":end})
        await db.execute(text("DELETE FROM rollup_tasks WHERE account_id=:account AND hour_start=:hour"), {"account":task["account_id"],"hour":task["hour_start"]})
    return True
