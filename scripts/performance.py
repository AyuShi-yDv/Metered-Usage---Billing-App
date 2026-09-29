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
        await conn.execute("DROP INDEX IF EXISTS billing_events_account_time_endpoint_idx")
        end=datetime.now(timezone.utc)
        start=end-timedelta(days=30)
        print("\n".join(row[0] for row in await conn.fetch(QUERY,UUID(ACCOUNT),start,end)))
        # Equality key first, range key second; endpoint follows the range for
        # p95/report coverage. duration_ms is included, not a search key.
        await conn.execute("CREATE INDEX billing_events_account_occurred_idx ON billing_events(account_id,occurred_at)")
        await conn.execute("CREATE INDEX billing_events_account_time_endpoint_idx ON billing_events(account_id,occurred_at,endpoint) INCLUDE(duration_ms)")
        await conn.execute("ANALYZE billing_events")
        print("AFTER INDEX")
        print("\n".join(row[0] for row in await conn.fetch(QUERY,UUID(ACCOUNT),start,end)))
    finally:
        await transaction.rollback()  # restore the database's original indexes
        await conn.close()

if __name__=="__main__": asyncio.run(main())
