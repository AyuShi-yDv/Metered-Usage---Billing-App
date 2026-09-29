# Reporting-query performance

The dashboard time-series query filters canonical `billing_events` by account and arbitrary timestamp bounds, groups billable statuses into hourly buckets, and left-joins a `generate_series` so empty buckets remain visible. Its benchmark is representative over a 30-day interval:

```sql
WITH buckets AS (
  SELECT generate_series(date_trunc('hour', $2::timestamptz),
    date_trunc('hour', $3::timestamptz - interval '1 microsecond'), interval '1 hour') AS bucket
), usage AS (
  SELECT date_trunc('hour', occurred_at) AS bucket,
    count(*) FILTER (WHERE status_code BETWEEN 200 AND 499) AS calls
  FROM billing_events
  WHERE account_id = $1::uuid AND occurred_at >= $2 AND occurred_at < $3
  GROUP BY 1
)
SELECT buckets.bucket, COALESCE(usage.calls, 0)::bigint AS billable_calls
FROM buckets LEFT JOIN usage USING (bucket)
ORDER BY buckets.bucket;
```

`docker compose --profile tools run --rm ops-tools performance.py` emits `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` before and after index creation inside a transaction that rolls back, preserving the original indexes. The candidate indexes are `(account_id, occurred_at)` for equality-then-range filtering and `(account_id, occurred_at, endpoint) INCLUDE (duration_ms)` for endpoint latency coverage; equality comes first, then the range key, and endpoint is last because it is a grouping/coverage value rather than a leading filter.

## Measurement status

No honest before/after measurements are available in this workspace: Docker and PostgreSQL tools/services are not installed, so the 500,000-event seed, planner selection, buffers, row-estimate accuracy, and wall-clock improvement have not been observed. After running the seed and benchmark against PostgreSQL 16, record the emitted plans, execution time, buffer reads/hits, scan type, estimated versus actual rows, and percent improvement here. Until then this requirement is incomplete; no synthetic plan output is substituted for a real measurement.
