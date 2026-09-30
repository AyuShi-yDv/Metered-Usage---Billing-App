from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text

from ..charges import WHAT_IF_SQL
from ..db import Session
from ..deps import require_account, require_finance, require_utc_offsets

router = APIRouter(tags=["accounts"])

# Whitelisted ORDER BY fragments: user input selects a key, it is never interpolated.
ORDERINGS = {
    ("usage", "desc"): "calls DESC", ("usage", "asc"): "calls ASC",
    ("name", "asc"): "a.name ASC", ("name", "desc"): "a.name DESC",
}
PLANS_SQL = text("SELECT id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents FROM plans ORDER BY monthly_base_fee_cents,id")


def like_pattern(search: str) -> str:
    escaped = search[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/plans")
async def plans(x_dashboard_token: str = Header(default="")):
    require_finance(x_dashboard_token)
    async with Session() as db:
        rows = (await db.execute(PLANS_SQL)).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.get("/accounts")
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = "",
    sort: str = Query("usage", pattern="^(usage|name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    x_dashboard_token: str = Header(default=""),
):
    require_finance(x_dashboard_token)
    sql = text(f"""
WITH usage AS (
  SELECT account_id, sum(billable_calls)::bigint AS calls
  FROM hourly_usage_rollups WHERE hour_start >= date_trunc('month', now()) GROUP BY account_id
)
SELECT a.id, a.name, COALESCE(u.calls, 0)::bigint AS calls, p.name AS plan_name, p.included_calls,
       count(*) OVER () AS total
FROM accounts a
LEFT JOIN usage u ON u.account_id = a.id
LEFT JOIN account_plans ap ON ap.account_id = a.id AND ap.effective_from <= now() AND (ap.effective_to IS NULL OR ap.effective_to > now())
LEFT JOIN plans p ON p.id = ap.plan_id
WHERE a.name ILIKE :search ESCAPE '\\'
ORDER BY {ORDERINGS[(sort, order)]}, a.id
LIMIT :limit OFFSET :offset""")
    async with Session() as db:
        rows = (await db.execute(sql, {"search": like_pattern(search), "limit": page_size, "offset": (page - 1) * page_size})).mappings().all()
    total = rows[0]["total"] if rows else 0
    return {"data": [{k: v for k, v in r.items() if k != "total"} for r in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/accounts/{account_id}")
async def account_detail(account_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    sql = text("""
WITH plan AS (
  SELECT p.name, p.included_calls, p.overage_cents_per_1000, p.monthly_base_fee_cents
  FROM account_plans ap JOIN plans p ON p.id = ap.plan_id
  WHERE ap.account_id = :account AND ap.effective_from <= now() AND (ap.effective_to IS NULL OR ap.effective_to > now())
  ORDER BY ap.effective_from DESC LIMIT 1
), usage AS (
  SELECT COALESCE(sum(billable_calls), 0)::bigint AS calls FROM hourly_usage_rollups
  WHERE account_id = :account AND hour_start >= date_trunc('month', now())
), latency AS (
  SELECT jsonb_agg(jsonb_build_object('endpoint', endpoint, 'p95_duration_ms', p95, 'calls', n) ORDER BY endpoint) AS endpoints
  FROM (SELECT endpoint, percentile_cont(.95) WITHIN GROUP (ORDER BY duration_ms) AS p95, count(*) AS n
        FROM billing_events WHERE account_id = :account AND occurred_at >= date_trunc('month', now()) GROUP BY endpoint) x
)
SELECT a.id, a.name AS account_name, plan.name AS plan_name, plan.included_calls, plan.overage_cents_per_1000,
       plan.monthly_base_fee_cents, usage.calls,
       round(GREATEST(usage.calls + ((usage.calls::numeric / GREATEST(EXTRACT(EPOCH FROM now() - date_trunc('month', now())), 1))
          * EXTRACT(EPOCH FROM (date_trunc('month', now()) + interval '1 month' - now()))) - plan.included_calls, 0)
          * plan.overage_cents_per_1000 / 1000)::bigint AS projected_overage_cents,
       COALESCE(latency.endpoints, '[]'::jsonb) AS endpoints
FROM accounts a CROSS JOIN plan CROSS JOIN usage CROSS JOIN latency WHERE a.id = :account""")
    async with Session() as db:
        row = (await db.execute(sql, {"account": account_id})).mappings().first()
    if not row:
        raise HTTPException(404, "account not found or has no active plan")
    return dict(row)


@router.get("/accounts/{account_id}/plans")
async def account_plans(account_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    async with Session() as db:
        rows = (await db.execute(PLANS_SQL)).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/accounts/{account_id}/plan-changes", status_code=201)
async def schedule_plan_change(account_id: UUID, plan_id: UUID, effective_at: datetime | None = None, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    effective_at = effective_at or datetime.now(timezone.utc)
    require_utc_offsets(effective_at)
    effective_at = effective_at.astimezone(timezone.utc)
    if effective_at < datetime.now(timezone.utc):
        raise HTTPException(422, "plan changes cannot be backdated")
    async with Session() as db, db.begin():
        if not (await db.execute(text("SELECT id FROM accounts WHERE id=:a FOR UPDATE"), {"a": account_id})).scalar_one_or_none():
            raise HTTPException(404, "account not found")
        if not (await db.execute(text("SELECT id FROM plans WHERE id=:p"), {"p": plan_id})).scalar_one_or_none():
            raise HTTPException(404, "plan not found")
        if (await db.execute(text("SELECT id FROM account_plans WHERE account_id=:a AND effective_from>now() LIMIT 1 FOR UPDATE"), {"a": account_id})).first():
            raise HTTPException(409, "an account can have only one pending plan change")
        current = (await db.execute(text(
            "SELECT id,effective_from FROM account_plans WHERE account_id=:a AND effective_from<=now() AND (effective_to IS NULL OR effective_to>now()) FOR UPDATE"),
            {"a": account_id})).mappings().first()
        if not current or effective_at <= current["effective_from"]:
            raise HTTPException(409, "effective time must follow the active plan start")
        await db.execute(text("UPDATE account_plans SET effective_to=:e WHERE id=:id"), {"e": effective_at, "id": current["id"]})
        assignment_id = uuid4()
        await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(:id,:a,:p,:e)"),
                         {"id": assignment_id, "a": account_id, "p": plan_id, "e": effective_at})
    return {"id": str(assignment_id), "account_id": str(account_id), "plan_id": str(plan_id), "effective_at": effective_at}


@router.get("/accounts/{account_id}/what-if")
async def what_if(account_id: UUID, plan_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    async with Session() as db:
        row = (await db.execute(WHAT_IF_SQL, {"account": account_id, "plan_id": plan_id})).mappings().first()
    if not row:
        raise HTTPException(404, "account, active plan, or comparison plan not found")
    return dict(row)
