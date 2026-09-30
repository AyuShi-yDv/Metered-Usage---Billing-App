"""Rollup correctness, re-run safety and concurrency (needs a migrated billing DB via DATABASE_URL)."""
import asyncio

from conftest import add_events, hour
from sqlalchemy import text

from app.worker import process_one_rollup, rollup_hour


async def rollup_rows(sessions, account):
    async with sessions() as db:
        return (await db.execute(text(
            "SELECT endpoint, billable_calls, total_calls FROM hourly_usage_rollups WHERE account_id=:a ORDER BY endpoint"),
            {"a": account})).all()


async def run_rollup(sessions, account, h):
    async with sessions() as db, db.begin():
        await rollup_hour(db, account, h)


async def test_5xx_is_not_billable_but_4xx_is(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 10, 200), (h, "/a", 10, 404), (h, "/a", 10, 503)])
    await run_rollup(sessions, t.account, h)
    assert [tuple(r) for r in await rollup_rows(sessions, t.account)] == [("/a", 2, 3)]


async def test_rerunning_the_same_hour_does_not_double_count(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 10, 200)] * 4)
    for _ in range(3):
        await run_rollup(sessions, t.account, h)
    assert [tuple(r) for r in await rollup_rows(sessions, t.account)] == [("/a", 4, 4)]


async def test_two_workers_rolling_up_the_same_hour_concurrently_do_not_double_count(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 10, 200)] * 7 + [(h, "/b", 10, 500)] * 2)
    # Both start together; the advisory lock makes the second wait and rebuild from committed data.
    await asyncio.gather(run_rollup(sessions, t.account, h), run_rollup(sessions, t.account, h))
    assert [tuple(r) for r in await rollup_rows(sessions, t.account)] == [("/a", 7, 7), ("/b", 0, 2)]


async def test_task_queue_workers_leave_a_correct_rollup_and_empty_queue(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 10, 200)] * 5)
    async with sessions() as db, db.begin():
        await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:a,:h)"), {"a": t.account, "h": h})

    async def drain():
        while await process_one_rollup():
            pass

    await asyncio.gather(drain(), drain())
    assert [tuple(r) for r in await rollup_rows(sessions, t.account)] == [("/a", 5, 5)]
    async with sessions() as db:
        assert await db.scalar(text("SELECT count(*) FROM rollup_tasks WHERE account_id=:a"), {"a": t.account}) == 0


async def test_late_event_is_recomputed_into_the_same_hour_not_added_twice(sessions, make_tenant):
    t = await make_tenant(); h = hour()
    await add_events(sessions, t.account, [(h, "/a", 10, 200)] * 2)
    await run_rollup(sessions, t.account, h)
    await add_events(sessions, t.account, [(h, "/a", 10, 200)])  # arrives after the first rollup
    await run_rollup(sessions, t.account, h)
    assert [tuple(r) for r in await rollup_rows(sessions, t.account)] == [("/a", 3, 3)]
