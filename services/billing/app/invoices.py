"""Invoice generation. Preview and finalize share `build_lines`, so what you preview is what is billed."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .charges import PERIOD_CHARGES_SQL
from .worker import month_floor, next_month

# Events may arrive up to 24h late; wait 48h after month end so ordinary late events land in the invoice.
GRACE = timedelta(hours=48)


def month_bounds(value: datetime) -> tuple[datetime, datetime]:
    start = month_floor(value)
    return start, next_month(start)


def is_closed(period_end: datetime, now: datetime | None = None) -> bool:
    return period_end <= (now or datetime.now(timezone.utc)) - GRACE


def plan_names(charges) -> str:
    return ", ".join(dict.fromkeys(s["plan_name"] for s in (charges["plan_segments"] or [])))


def build_lines(charges) -> list[dict]:
    """Line items whose amounts sum exactly to total_cents (the usage line is informational, 0 cents)."""
    names = plan_names(charges)
    overage_calls = int(charges["overage_calls"] or 0)
    return [
        {"description": f"Billable API calls in period ({names})", "quantity": int(charges["calls"]), "amount_cents": 0},
        {"description": f"Monthly base fee, prorated by plan ({names})", "quantity": 1, "amount_cents": int(charges["base_fee_cents"])},
        {"description": f"Overage: {overage_calls:,} calls beyond included allowance", "quantity": overage_calls, "amount_cents": int(charges["overage_cents"])},
    ]


async def fetch_charges(db: AsyncSession, account_id: UUID, start: datetime, end: datetime):
    charges = (await db.execute(PERIOD_CHARGES_SQL, {"account": account_id, "start": start, "end": end})).mappings().first()
    if not charges or charges["base_fee_cents"] is None:
        raise HTTPException(404, "account has no plan in this period")
    return charges


async def preview(db: AsyncSession, account_id: UUID, period_start: datetime) -> dict:
    start, end = month_bounds(period_start)
    charges = await fetch_charges(db, account_id, start, end)
    pending = (await db.execute(
        text("SELECT COALESCE(sum(amount_cents),0) FROM late_adjustments WHERE account_id=:account AND applied_invoice_id IS NULL"),
        {"account": account_id})).scalar_one()
    return {
        "period_start": start, "period_end": end, "plan_name": plan_names(charges),
        "calls": int(charges["calls"]), "overage_calls": int(charges["overage_calls"] or 0),
        "base_fee_cents": charges["base_fee_cents"], "overage_cents": charges["overage_cents"],
        "total_cents": charges["total_cents"], "lines": build_lines(charges),
        "pending_adjustments_cents": int(pending), "finalizable": is_closed(end),
    }


async def finalize(db: AsyncSession, account_id: UUID, period_start: datetime) -> dict:
    """Create the invoice exactly once per (account, period); repeats return the existing invoice."""
    start, end = month_bounds(period_start)
    if not is_closed(end):
        raise HTTPException(409, "invoice period is not closed; it closes 48 hours after month end")
    # Serialise concurrent finalize calls for the same account+period (UNIQUE(account, period) is the backstop).
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": f"invoice:{account_id}:{start.isoformat()}"})
    charges = await fetch_charges(db, account_id, start, end)
    invoice_id = uuid4()
    inserted = (await db.execute(text(
        "INSERT INTO invoices(id,account_id,period_start,period_end,status,base_fee_cents,overage_cents,total_cents) "
        "VALUES(:id,:account,:start,:end,'final',:base,:overage,:total) ON CONFLICT(account_id,period_start) DO NOTHING RETURNING id"),
        {"id": invoice_id, "account": account_id, "start": start, "end": end, "base": charges["base_fee_cents"],
         "overage": charges["overage_cents"], "total": charges["total_cents"]})).scalar_one_or_none()
    if not inserted:
        existing = (await db.execute(text("SELECT id,total_cents FROM invoices WHERE account_id=:account AND period_start=:start"),
                                     {"account": account_id, "start": start})).mappings().one()
        return {"invoice_id": str(existing["id"]), "total_cents": existing["total_cents"], "created": False}
    for line in build_lines(charges):
        await db.execute(text("INSERT INTO invoice_lines(id,invoice_id,description,quantity,amount_cents) VALUES(:id,:invoice,:d,:q,:a)"),
                         {"id": uuid4(), "invoice": invoice_id, "d": line["description"], "q": line["quantity"], "a": line["amount_cents"]})
    adjustments = (await db.execute(
        text("SELECT id,amount_cents,source_period_start FROM late_adjustments WHERE account_id=:account AND applied_invoice_id IS NULL FOR UPDATE"),
        {"account": account_id})).mappings().all()
    adjustment_total = 0
    for row in adjustments:
        await db.execute(text("INSERT INTO invoice_lines(id,invoice_id,description,quantity,amount_cents,source_period_start) VALUES(:id,:invoice,:d,1,:a,:s)"),
                         {"id": uuid4(), "invoice": invoice_id, "d": "Late usage adjustment from an earlier period", "a": row["amount_cents"], "s": row["source_period_start"]})
        await db.execute(text("UPDATE late_adjustments SET applied_invoice_id=:invoice WHERE id=:id"), {"invoice": invoice_id, "id": row["id"]})
        adjustment_total += row["amount_cents"]
    if adjustment_total:
        await db.execute(text("UPDATE invoices SET total_cents=total_cents+:a WHERE id=:id"), {"a": adjustment_total, "id": invoice_id})
    return {"invoice_id": str(invoice_id), "total_cents": charges["total_cents"] + adjustment_total, "created": True}
