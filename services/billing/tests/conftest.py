import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HAS_DB = bool(os.getenv("DATABASE_URL"))  # DB-backed tests skip themselves when there is no migrated database
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost/unused")
os.environ.setdefault("RABBITMQ_URL", "amqp://unused")
os.environ.setdefault("INTERNAL_TOKEN", "test-only-token")
os.environ.setdefault("DASHBOARD_TOKEN", "test-finance-token")

UTC = timezone.utc


@dataclass
class Tenant:
    account: uuid.UUID
    plan: uuid.UUID


@pytest.fixture
async def sessions():
    if not HAS_DB:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"timezone": "UTC"}})
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
    from app.db import engine as app_engine  # the app's pool belongs to this test's event loop
    await app_engine.dispose()


@pytest.fixture
async def make_tenant(sessions):
    """Factory: an isolated account on its own plan (effective since 2020); everything is deleted afterwards."""
    created: list[Tenant] = []

    async def factory(included=1000, per_1000=500, base=1000) -> Tenant:
        tenant = Tenant(uuid.uuid4(), uuid.uuid4())
        async with sessions() as db, db.begin():
            await db.execute(text("INSERT INTO accounts(id,name) VALUES(:a,:n)"), {"a": tenant.account, "n": f"test-{tenant.account}"})
            await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:p,:n,:i,:o,:b)"),
                             {"p": tenant.plan, "n": f"test-{tenant.plan}", "i": included, "o": per_1000, "b": base})
            await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(gen_random_uuid(),:a,:p,'2020-01-01T00:00:00Z')"),
                             {"a": tenant.account, "p": tenant.plan})
        created.append(tenant)
        return tenant

    yield factory
    async with sessions() as db, db.begin():
        for t in created:
            params = {"a": t.account, "p": t.plan}
            for sql in (
                "DELETE FROM invoice_lines WHERE invoice_id IN (SELECT id FROM invoices WHERE account_id=:a)",
                "DELETE FROM late_adjustments WHERE account_id=:a", "DELETE FROM invoices WHERE account_id=:a",
                "DELETE FROM rollup_tasks WHERE account_id=:a", "DELETE FROM hourly_usage_rollups WHERE account_id=:a",
                "DELETE FROM billing_events WHERE account_id=:a", "DELETE FROM account_plans WHERE account_id=:a",
                "DELETE FROM accounts WHERE id=:a", "DELETE FROM plans WHERE id=:p",
            ):
                await db.execute(text(sql), params)


async def add_events(sessions, account, rows):
    """rows: iterable of (occurred_at, endpoint, duration_ms, status_code)."""
    async with sessions() as db, db.begin():
        await db.execute(
            text("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) "
                 "VALUES(gen_random_uuid(),:a,:e,:t,:d,:s)"),
            [{"a": account, "t": t, "e": e, "d": d, "s": s} for t, e, d, s in rows])


def hour(y=2024, m=3, d=10, h=0) -> datetime:
    return datetime(y, m, d, h, tzinfo=UTC)
