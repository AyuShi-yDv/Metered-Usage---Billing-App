"""Capture the main zero-filled time-series plan before and after its indexes."""
import asyncio, os
from datetime import datetime, timedelta, timezone
from uuid import UUID
import asyncpg

DSN=os.environ["BILLING_DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://")
ACCOUNT=os.environ.get("BENCH_ACCOUNT_ID","00000000-0000-0000-0000-000000000001")
QUERY="""EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
WITH buckets AS (
  SELECT generate_series(date_trunc('hour',$2::timestamptz),
    date_trunc('hour',$3::timestamptz-interval '1 microsecond'),interval '1 hour') AS bucket
), usage AS (
  SELECT date_trunc('hour',occurred_at) AS bucket,
    count(*) FILTER(WHERE status_code BETWEEN 200 AND 499) AS calls
  FROM billing_events
  WHERE account_id=$1::uuid AND occurred_at >= $2 AND occurred_at < $3
  GROUP BY 1
)
SELECT buckets.bucket,COALESCE(usage.calls,0)::bigint AS billable_calls
FROM buckets LEFT JOIN usage USING(bucket) ORDER BY buckets.bucket"""

async def main():
    conn=await asyncpg.connect(DSN)
    transaction=conn.transaction()
    await transaction.start()
    try:
        print("BEFORE INDEX")
        await conn.execute("DROP INDEX IF EXISTS billing_events_account_occurred_idx")
        await conn.execute("DROP INDEX IF EXISTS billing_events_account_time_endpoint_idx")  # dropped by migration 0002 already
        await conn.execute("ANALYZE billing_events")
        end=datetime.now(timezone.utc)
        start=end-timedelta(days=30)
        for label in ("run 1 (cold)","run 2 (warm)"):
            print(f"-- {label}"); print("\n".join(row[0] for row in await conn.fetch(QUERY,UUID(ACCOUNT),start,end)))
        # Equality column (account_id) first, range column (occurred_at) second: the btree can then
        # seek to one account and read a contiguous time slice.
        await conn.execute("CREATE INDEX billing_events_account_occurred_idx ON billing_events(account_id,occurred_at)")
        await conn.execute("ANALYZE billing_events")
        print("AFTER INDEX")
        for label in ("run 1","run 2 (warm)"):
            print(f"-- {label}"); print("\n".join(row[0] for row in await conn.fetch(QUERY,UUID(ACCOUNT),start,end)))
    finally:
        await transaction.rollback()  # restore the database's original indexes
        await conn.close()

if __name__=="__main__": asyncio.run(main())
