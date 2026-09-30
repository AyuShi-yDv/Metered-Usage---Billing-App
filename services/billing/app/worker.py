"""Hourly rollups. Always *recomputed* from billing_events, never incremented, so re-running is safe."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .charges import PERIOD_CHARGES_SQL
from .db import Session

ADVISORY_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))")
DELETE_ROLLUP_SQL = text("DELETE FROM hourly_usage_rollups WHERE account_id=:account AND hour_start=:hour")
INSERT_ROLLUP_SQL = text("""
INSERT INTO hourly_usage_rollups(account_id, hour_start, endpoint, billable_calls, total_calls)
SELECT account_id, date_trunc('hour', occurred_at), endpoint,
       count(*) FILTER (WHERE (status_code BETWEEN 200 AND 299 OR status_code BETWEEN 400 AND 499)), count(*)
FROM billing_events
WHERE account_id=:account AND occurred_at >= :hour AND occurred_at < :end
GROUP BY account_id, date_trunc('hour', occurred_at), endpoint
""")


def hour_floor(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def month_floor(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(month_start: datetime) -> datetime:
    return (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)


async def rollup_hour(db: AsyncSession, account_id: UUID, hour_start: datetime) -> None:
    """Replace one (account, hour) rollup with a fresh aggregate, inside the caller's transaction.

    A transaction-scoped advisory lock keyed on (account, month) serialises concurrent workers: the
    second one waits, then deletes and rebuilds from committed data, so nothing is counted twice.
    Without the lock two workers would both DELETE nothing and both INSERT (PK violation/double count).
    """
    hour_start = hour_floor(hour_start)
    await db.execute(ADVISORY_LOCK_SQL, {"scope": f"{account_id}:{month_floor(hour_start).isoformat()}"})
    await db.execute(DELETE_ROLLUP_SQL, {"account": account_id, "hour": hour_start})
    await db.execute(INSERT_ROLLUP_SQL, {"account": account_id, "hour": hour_start, "end": hour_start + timedelta(hours=1)})


async def reconcile_late_usage(db: AsyncSession, account_id: UUID, month_start: datetime) -> None:
    """If the month is already invoiced, record the extra overage as an adjustment for the next invoice.

    Final invoices are immutable. The adjustment is the overage now owed minus what was invoiced minus
    adjustments already recorded, so repeated calls never double-charge.
    """
    finalized = (await db.execute(
        text("SELECT id, overage_cents FROM invoices WHERE account_id=:account AND period_start=:month AND status='final'"),
        {"account": account_id, "month": month_start})).mappings().first()
    if not finalized:
        return
    charges = (await db.execute(PERIOD_CHARGES_SQL, {"account": account_id, "start": month_start, "end": next_month(month_start)})).mappings().first()
    already = (await db.execute(
        text("SELECT COALESCE(sum(amount_cents),0) FROM late_adjustments WHERE account_id=:account AND source_period_start=:month"),
        {"account": account_id, "month": month_start})).scalar_one()
    owed = max(0, (charges["overage_cents"] or 0) - finalized["overage_cents"])
    if owed > already:
        await db.execute(
            text("INSERT INTO late_adjustments(id,account_id,source_period_start,amount_cents) VALUES(gen_random_uuid(),:account,:month,:amount)"),
            {"account": account_id, "month": month_start, "amount": owed - already})


async def process_one_rollup() -> bool:
    """Claim one pending (account, hour) task. SKIP LOCKED lets several workers run side by side."""
    async with Session() as db, db.begin():
        task = (await db.execute(text(
            "SELECT account_id, hour_start FROM rollup_tasks ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"))).mappings().first()
        if not task:
            return False
        account_id, hour_start = task["account_id"], task["hour_start"]
        await rollup_hour(db, account_id, hour_start)
        await db.execute(text("DELETE FROM rollup_tasks WHERE account_id=:account AND hour_start=:hour"), {"account": account_id, "hour": hour_start})
        await reconcile_late_usage(db, account_id, month_floor(hour_start))
    return True
