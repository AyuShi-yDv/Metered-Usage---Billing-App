"""Executes the real report SQL against real rows (needs DATABASE_URL)."""
from datetime import datetime, timedelta

import pytest
from conftest import UTC, add_events, hour
from sqlalchemy import text

from app.reports import MTD_SQL, P95_SQL, TIME_SERIES_SQL, TOP_OVERAGE_SQL
from app.worker import month_floor

HOUR, DAY = timedelta(hours=1), timedelta(days=1)


async def series(sessions, account, start, end, granularity="hour"):
    async with sessions() as db:
        rows = (await db.execute(text(TIME_SERIES_SQL), {
            "account_id": account, "start": start, "end": end, "bucket": granularity,
            "interval": HOUR if granularity == "hour" else DAY})).all()
    return [(r.bucket, r.billable_calls) for r in rows]


async def test_hourly_series_zero_fills_gaps_and_excludes_5xx(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 1, 200)] * 3 + [(h, "/a", 1, 500)] * 4 + [(h + 3 * HOUR, "/a", 1, 404)])
    result = await series(sessions, t.account, h, h + 5 * HOUR)
    assert [calls for _, calls in result] == [3, 0, 0, 1, 0]   # the empty hours are present as zeros
    assert [b for b, _ in result] == [h + i * HOUR for i in range(5)]


async def test_series_does_not_count_redirects_or_informational_responses(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 1, code) for code in (100, 200, 301, 304, 404, 500)])
    assert [c for _, c in await series(sessions, t.account, h, h + HOUR)] == [2]   # only 200 and 404


async def test_series_with_no_events_at_all_is_all_zeros(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    assert [c for _, c in await series(sessions, t.account, h, h + 4 * HOUR)] == [0, 0, 0, 0]


async def test_unaligned_range_still_covers_partial_first_and_last_buckets(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h + timedelta(minutes=50), "/a", 1, 200), (h + timedelta(hours=2, minutes=10), "/a", 1, 200)])
    result = await series(sessions, t.account, h + timedelta(minutes=30), h + timedelta(hours=2, minutes=30))
    assert [c for _, c in result] == [1, 0, 1]


async def test_daily_series_buckets_on_utc_midnight(sessions, make_tenant):
    t = await make_tenant(); d = hour()
    await add_events(sessions, t.account, [(d + timedelta(hours=23), "/a", 1, 200), (d + DAY + timedelta(hours=1), "/a", 1, 200), (d + DAY + timedelta(hours=2), "/a", 1, 201)])
    result = await series(sessions, t.account, d, d + 3 * DAY, "day")
    assert [c for _, c in result] == [1, 2, 0]


async def test_other_accounts_events_never_leak_into_a_series(sessions, make_tenant):
    a, b = await make_tenant(), await make_tenant(); h = hour()
    await add_events(sessions, a.account, [(h, "/a", 1, 200)] * 2)
    await add_events(sessions, b.account, [(h, "/a", 1, 200)] * 9)
    assert [c for _, c in await series(sessions, a.account, h, h + HOUR)] == [2]


async def test_p95_is_percentile_cont_per_endpoint(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/slow", ms, 200) for ms in range(1, 101)] + [(h, "/fast", 7, 200)] * 5)
    async with sessions() as db:
        rows = (await db.execute(text(P95_SQL), {"account_id": t.account, "start": h, "end": h + HOUR})).all()
    by_endpoint = {r.endpoint: r.p95_duration_ms for r in rows}
    assert by_endpoint["/slow"] == pytest.approx(95.05)   # 1..100: position 0.95*99 = 94.05 -> 95.05
    assert by_endpoint["/fast"] == pytest.approx(7)


async def add_rollup(sessions, account, hour_start, calls):
    async with sessions() as db, db.begin():
        await db.execute(text("INSERT INTO hourly_usage_rollups(account_id,hour_start,endpoint,billable_calls,total_calls) VALUES(:a,:h,'/a',:c,:c)"),
                         {"a": account, "h": hour_start, "c": calls})


async def test_month_to_date_reports_overage_and_a_projection(sessions, make_tenant):
    t = await make_tenant(included=1000, per_1000=500)
    await add_rollup(sessions, t.account, month_floor(datetime.now(UTC)), 5000)
    async with sessions() as db:
        row = (await db.execute(text(MTD_SQL), {"account_id": t.account})).mappings().one()
    assert (row["calls"], row["included_calls"], row["overage_calls"]) == (5000, 1000, 4000)
    assert row["projected_overage_calls"] >= 4000 and row["projected_overage_cents"] >= 2000  # 4000 calls * 500c / 1000


async def test_top_overage_uses_dense_rank_and_month_over_month_change(sessions, make_tenant):
    top, tie_a, tie_b = await make_tenant(included=1000, per_1000=500), await make_tenant(included=1000, per_1000=500), await make_tenant(included=1000, per_1000=500)
    current = month_floor(datetime.now(UTC)); previous = month_floor(current - timedelta(days=1))
    await add_rollup(sessions, top.account, current, 10_000_000); await add_rollup(sessions, top.account, previous, 4_000_000)
    for t in (tie_a, tie_b):
        await add_rollup(sessions, t.account, current, 9_000_000)
    async with sessions() as db:
        rows = {str(r["id"]): r for r in (await db.execute(text(TOP_OVERAGE_SQL))).mappings().all()}
    first, second, third = rows[str(top.account)], rows[str(tie_a.account)], rows[str(tie_b.account)]
    assert first["overage_cents"] == 4_999_500 and first["previous_overage_cents"] == 1_999_500
    assert first["month_over_month_change_cents"] == 3_000_000
    assert first["rank"] < second["rank"] == third["rank"]          # DENSE_RANK: the two equal accounts tie
    assert all(r["overage_cents"] > 0 for r in rows.values())       # accounts with no overage are never listed
