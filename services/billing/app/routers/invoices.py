from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header
from sqlalchemy import text

from .. import invoices as service
from ..db import Session
from ..deps import require_account, require_utc_offsets

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/preview/{account_id}/{period_start}")
async def invoice_preview(account_id: UUID, period_start: datetime, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    require_utc_offsets(period_start)
    async with Session() as db:
        return await service.preview(db, account_id, period_start)


@router.post("/{account_id}/{period_start}")
async def create_invoice(account_id: UUID, period_start: datetime, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    require_utc_offsets(period_start)
    async with Session() as db, db.begin():
        return await service.finalize(db, account_id, period_start)


@router.get("/{account_id}")
async def list_invoices(account_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    sql = text("""
SELECT i.id, i.account_id, i.period_start, i.period_end, i.status, i.base_fee_cents, i.overage_cents, i.total_cents,
       COALESCE(jsonb_agg(to_jsonb(l) - 'invoice_id' ORDER BY l.description) FILTER (WHERE l.id IS NOT NULL), '[]'::jsonb) AS lines
FROM invoices i LEFT JOIN invoice_lines l ON l.invoice_id = i.id
WHERE i.account_id = :account GROUP BY i.id ORDER BY i.period_start DESC""")
    async with Session() as db:
        rows = (await db.execute(sql, {"account": account_id})).mappings().all()
    return {"data": [dict(r) for r in rows]}
