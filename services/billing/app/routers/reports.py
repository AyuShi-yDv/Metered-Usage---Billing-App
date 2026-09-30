"""GET /reports/usage — four reports, each exactly one SQL statement (no Python loops, no N+1)."""
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text

from ..db import Session
from ..deps import require_account, require_finance, require_utc_offsets
from ..reports import MTD_SQL, P95_SQL, TIME_SERIES_SQL, TOP_OVERAGE_SQL

router = APIRouter(prefix="/reports", tags=["reports"])

# generate_series materialises one row per bucket, so the range must be bounded.
MAX_SPAN = {"hour": timedelta(days=92), "day": timedelta(days=1100)}
STEP = {"hour": timedelta(hours=1), "day": timedelta(days=1)}


@router.get("/usage")
async def usage_report(
    report: Literal["time_series", "p95", "mtd", "top_overage"] = Query(...),
    account_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    granularity: Literal["hour", "day"] = "hour",
    x_dashboard_token: str = Header(default=""),
):
    if report == "top_overage":
        require_finance(x_dashboard_token)
        async with Session() as db:
            rows = (await db.execute(text(TOP_OVERAGE_SQL))).mappings().all()
        return {"data": [dict(r) for r in rows]}

    if account_id is None:
        raise HTTPException(422, "account_id is required")
    require_account(account_id, x_dashboard_token)

    if report == "mtd":
        async with Session() as db:
            row = (await db.execute(text(MTD_SQL), {"account_id": account_id})).mappings().first()
        if not row:
            raise HTTPException(404, "account or active plan not found")
        return dict(row)

    if start is None or end is None:
        raise HTTPException(422, "start and end are required")
    require_utc_offsets(start, end)
    if end <= start:
        raise HTTPException(422, "end must be after start")
    if end - start > MAX_SPAN[granularity]:
        raise HTTPException(422, f"range too large for {granularity} granularity (max {MAX_SPAN[granularity].days} days)")

    if report == "p95":
        sql, params = P95_SQL, {"account_id": account_id, "start": start, "end": end}
    else:
        sql, params = TIME_SERIES_SQL, {"account_id": account_id, "start": start, "end": end,
                                        "bucket": granularity, "interval": STEP[granularity]}
    async with Session() as db:
        rows = (await db.execute(text(sql), params)).mappings().all()
    return {"data": [dict(r) for r in rows]}
