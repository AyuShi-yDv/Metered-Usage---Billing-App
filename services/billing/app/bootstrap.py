"""Idempotent demo business data (plans + demo account). Schema always comes from Alembic."""
from uuid import UUID

from sqlalchemy import text

from .db import Session

DEMO_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
PLANS = (
    (UUID("00000000-0000-0000-0000-000000000010"), "Starter", 10_000, 250, 1_900),
    (UUID("00000000-0000-0000-0000-000000000012"), "Growth", 50_000, 180, 7_900),
    (UUID("00000000-0000-0000-0000-000000000013"), "Scale", 250_000, 120, 29_900),
)


async def seed_demo() -> None:
    async with Session() as db, db.begin():
        await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'Demo account') ON CONFLICT DO NOTHING"), {"id": DEMO_ACCOUNT_ID})
        for plan_id, name, included, per_1000, base in PLANS:
            await db.execute(
                text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) "
                     "VALUES(:id,:name,:included,:per,:base) ON CONFLICT DO NOTHING"),
                {"id": plan_id, "name": name, "included": included, "per": per_1000, "base": base})
        await db.execute(
            text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) "
                 "VALUES(:id,:account,:plan,'2020-01-01T00:00:00Z') ON CONFLICT DO NOTHING"),
            {"id": UUID("00000000-0000-0000-0000-000000000011"), "account": DEMO_ACCOUNT_ID, "plan": PLANS[0][0]})
