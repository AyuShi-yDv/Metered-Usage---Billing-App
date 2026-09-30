"""Bulk-load realistic demo/benchmark data (default 500,000 events over 60 days, 50 accounts).

Idempotent: skipped when the billing database already holds >= 90% of the target volume.
Account volume is Zipf-skewed so a handful of accounts exceed their plan allowance (otherwise the
overage reports would be empty). ~1% of events are re-delivered duplicates; the event_id primary
keys must discard them. Rollups are computed with one INSERT ... SELECT.
"""
import asyncio
import hashlib
import os
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

INGEST_DB = os.environ["INGEST_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
BILLING_DB = os.environ["BILLING_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
EVENT_COUNT = int(os.getenv("SEED_EVENTS", "500000"))
ACCOUNT_COUNT = 50
ENDPOINTS = ("/v1/search", "/v1/files", "/v1/export", "/v1/users")
STATUSES = (200, 200, 200, 201, 204, 400, 404, 429, 500, 503)   # ~20% are 5xx and must not be billed
COLUMNS = ["event_id", "account_id", "endpoint", "occurred_at", "duration_ms", "status_code"]
BATCH = 10_000


async def main() -> None:
    CLOCK_NOW = datetime.now(timezone.utc)
    ingest, billing = await asyncpg.connect(INGEST_DB), await asyncpg.connect(BILLING_DB)
    try:
        existing = await billing.fetchval("SELECT count(*) FROM billing_events")
        if existing >= EVENT_COUNT * 0.9:
            print(f"billing_events already holds {existing:,} rows; skipping seed")
            return
        demo = uuid.UUID("00000000-0000-0000-0000-000000000001")
        accounts = [demo] + [uuid.uuid5(uuid.NAMESPACE_DNS, f"metered-demo-{i}") for i in range(1, ACCOUNT_COUNT)]
        weights = [1 / (i + 1) ** 0.9 for i in range(ACCOUNT_COUNT)]          # account 0 (demo) is the heaviest
        plans = [uuid.uuid5(uuid.NAMESPACE_DNS, f"metered-plan-{i}") for i in range(3)]
        await billing.executemany(
            "INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
            [(plans[0], "Seed Starter", 10_000, 250, 1_900), (plans[1], "Seed Growth", 50_000, 180, 7_900), (plans[2], "Seed Scale", 250_000, 120, 29_900)])
        await billing.executemany("INSERT INTO accounts(id,name) VALUES($1,$2) ON CONFLICT(id) DO NOTHING",
                                  [(a, "Demo account" if a == demo else f"Demo account {i + 1:02d}") for i, a in enumerate(accounts)])
        await billing.executemany(
            "INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            [(uuid.uuid5(uuid.NAMESPACE_DNS, f"assignment-{a}"), a, plans[i % 3], datetime(2020, 1, 1, tzinfo=timezone.utc))
             for i, a in enumerate(accounts) if a != demo])            # the demo account keeps the Starter plan from startup
        key_ids = {a: uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-key-{a}") for a in accounts}

        def discarded_secret_hash() -> str:   # seeded keys are never usable: their secret is thrown away
            salt = secrets.token_bytes(16)
            return salt.hex() + ":" + hashlib.sha256(salt + secrets.token_bytes(32)).hexdigest()

        await ingest.executemany("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES($1,$2,$3,$4) ON CONFLICT(id) DO NOTHING",
                                 [(key_ids[a], a, f"seed{i:04d}", discarded_secret_hash()) for i, a in enumerate(accounts)])
        await billing.execute("CREATE TEMP TABLE seed_billing (LIKE billing_events INCLUDING DEFAULTS)")
        await ingest.execute("CREATE TEMP TABLE seed_ingest (LIKE usage_events INCLUDING DEFAULTS)")

        async def flush(rows: list[tuple]) -> None:
            await billing.copy_records_to_table("seed_billing", records=rows, columns=COLUMNS)
            await ingest.copy_records_to_table(
                "seed_ingest", columns=["event_id", "account_id", "api_key_id", "endpoint", "occurred_at", "duration_ms", "status_code"],
                records=[(r[0], r[1], key_ids[r[1]], *r[2:]) for r in rows])

        sent = 0
        while sent < EVENT_COUNT:
            n = min(BATCH, EVENT_COUNT - sent)
            rows = [(uuid.uuid4(), a, random.choice(ENDPOINTS),
                     CLOCK_NOW - timedelta(seconds=random.randrange(0, 60 * 86400)),
                     random.randint(1, 5000), random.choice(STATUSES))
                    for a in random.choices(accounts, weights, k=n)]
            rows += rows[::100]                                     # re-delivered duplicates, discarded by event_id PK
            await flush(rows)
            sent += n
        await billing.execute(f"INSERT INTO billing_events({','.join(COLUMNS)}) SELECT {','.join(COLUMNS)} FROM seed_billing ON CONFLICT(event_id) DO NOTHING")
        await ingest.execute("INSERT INTO usage_events(event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code) "
                             "SELECT event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code FROM seed_ingest ON CONFLICT(event_id) DO NOTHING")
        await billing.execute("""
            INSERT INTO hourly_usage_rollups(account_id,hour_start,endpoint,billable_calls,total_calls)
            SELECT account_id, date_trunc('hour',occurred_at), endpoint, count(*) FILTER (WHERE (status_code BETWEEN 200 AND 299 OR status_code BETWEEN 400 AND 499)), count(*)
            FROM billing_events GROUP BY 1,2,3
            ON CONFLICT(account_id,hour_start,endpoint) DO UPDATE SET billable_calls=excluded.billable_calls,total_calls=excluded.total_calls""")
        await billing.execute("ANALYZE billing_events")
        await billing.execute("ANALYZE hourly_usage_rollups")
        total = await billing.fetchval("SELECT count(*) FROM billing_events")
        print(f"Seeded {total:,} unique events across {ACCOUNT_COUNT} accounts and 3 plans (duplicates discarded by PK); spans 60 days.")
    finally:
        await ingest.close()
        await billing.close()


if __name__ == "__main__":
    asyncio.run(main())
