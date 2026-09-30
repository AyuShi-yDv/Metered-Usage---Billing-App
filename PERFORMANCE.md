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

## Measurements

Measured on 2026-09-29 with Docker Engine 29.8.1, Docker Compose 5.5.1, PostgreSQL 16.4, and the default demo account (`00000000-0000-0000-0000-000000000001`). The seed tool reported 505,000 attempted deliveries, with the event-id constraints retaining 500,000 unique events across 50 accounts and 3 plans. Seed event times span 60 days.

The query measured was the 30-day, hourly, zero-filled usage query shown above. The actual interval was `2026-08-30 13:52:35.008467+00` through `2026-09-29 13:52:35.008467+00`; the result plan produced 721 hourly buckets.

### Before candidate indexes

```text
Merge Left Join  (cost=11738.11..12004.97 rows=23805 width=16) (actual time=110.186..119.363 rows=721 loops=1)
  Merge Cond: ((generate_series(date_trunc('hour'::text, '2026-08-30 13:52:35.008467+00'::timestamp with time zone), date_trunc('hour'::text, ('2026-09-29 13:52:35.008467+00'::timestamp with time zone - '00:00:00.000001'::interval)), '01:00:00'::interval)) = usage.bucket)
  Buffers: shared hit=5725 read=448
  ->  Sort  (cost=54.85..57.35 rows=1000 width=8) (actual time=0.319..0.417 rows=721 loops=1)
        Sort Key: (generate_series(date_trunc('hour'::text, '2026-08-30 13:52:35.008467+00'::timestamp with time zone), date_trunc('hour'::text, ('2026-09-29 13:52:35.008467+00'::timestamp with time zone - '00:00:00.000001'::interval)), '01:00:00'::interval))
        Sort Method: quicksort  Memory: 25kB
        ->  ProjectSet  (cost=0.00..5.03 rows=1000 width=8) (actual time=0.024..0.187 rows=721 loops=1)
              ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
  ->  Sort  (cost=11683.26..11695.16 rows=4761 width=16) (actual time=109.761..118.354 rows=720 loops=1)
        Sort Key: usage.bucket
        Sort Method: quicksort  Memory: 53kB
        Buffers: shared hit=5725 read=448
        ->  Subquery Scan on usage  (cost=11285.31..11392.43 rows=4761 width=16) (actual time=108.661..117.664 rows=720 loops=1)
              Buffers: shared hit=5725 read=448
              ->  Finalize HashAggregate  (cost=11285.31..11344.82 rows=4761 width=16) (actual time=108.659..117.499 rows=720 loops=1)
                    Group Key: (date_trunc('hour'::text, billing_events.occurred_at))
                    Batches: 1  Memory Usage: 273kB
                    Buffers: shared hit=5725 read=448
                    ->  Gather  (cost=10843.65..11265.46 rows=3970 width=16) (actual time=103.579..113.580 rows=1945 loops=1)
                          Workers Planned: 2
                          Workers Launched: 2
                          Buffers: shared hit=5725 read=448
                          ->  Partial HashAggregate  (cost=9843.65..9868.46 rows=1985 width=16) (actual time=83.543..83.871 rows=648 loops=3)
                                Group Key: date_trunc('hour'::text, billing_events.occurred_at)
                                Batches: 1  Memory Usage: 177kB
                                Worker 0:  Batches: 1  Memory Usage: 177kB
                                Worker 1:  Batches: 1  Memory Usage: 177kB
                                ->  Parallel Seq Scan on billing_events  (cost=0.00..9823.80 rows=1985 width=10) (actual time=0.110..78.622 rows=1658 loops=3)
                                      Filter: ((occurred_at >= '2026-08-30 13:52:35.008467+00'::timestamp with time zone) AND (occurred_at < '2026-09-29 13:52:35.008467+00'::timestamp with time zone) AND (account_id = '00000000-0000-0000-0000-000000000001'::uuid))
                                      Rows Removed by Filter: 165008
                                      Buffers: shared hit=5725 read=448
Planning:
  Buffers: shared hit=86 read=1
Planning Time: 4.035 ms
Execution Time: 121.495 ms
```

### After candidate indexes

```text
Merge Left Join  (cost=6928.47..7209.79 rows=25120 width=16) (actual time=17.267..17.892 rows=721 loops=1)
  Merge Cond: ((generate_series(date_trunc('hour'::text, '2026-08-30 13:52:35.008467+00'::timestamp with time zone), date_trunc('hour'::text, ('2026-09-29 13:52:35.008467+00'::timestamp with time zone - '00:00:00.000001'::interval)), '01:00:00'::interval)) = usage.bucket)
  Buffers: shared hit=3304 read=170
  ->  Sort  (cost=54.85..57.35 rows=1000 width=8) (actual time=0.146..0.192 rows=721 loops=1)
        Sort Key: (generate_series(date_trunc('hour'::text, '2026-08-30 13:52:35.008467+00'::timestamp with time zone), date_trunc('hour'::text, ('2026-09-29 13:52:35.008467+00'::timestamp with time zone - '00:00:00.000001'::interval)), '01:00:00'::interval))
        Sort Method: quicksort  Memory: 25kB
        ->  ProjectSet  (cost=0.00..5.03 rows=1000 width=8) (actual time=0.009..0.073 rows=721 loops=1)
              ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.002..0.002 rows=1 loops=1)
  ->  Sort  (cost=6873.61..6886.17 rows=5024 width=16) (actual time=17.116..17.176 rows=720 loops=1)
        Sort Key: usage.bucket
        Sort Method: quicksort  Memory: 53kB
        Buffers: shared hit=3304 read=170
        ->  Subquery Scan on usage  (cost=6451.73..6564.77 rows=5024 width=16) (actual time=16.443..16.795 rows=720 loops=1)
              Buffers: shared hit=3304 read=170
              ->  HashAggregate  (cost=6451.73..6514.53 rows=5024 width=16) (actual time=16.441..16.619 rows=720 loops=1)
                    Group Key: date_trunc('hour'::text, billing_events.occurred_at)
                    Batches: 1  Memory Usage: 273kB
                    Buffers: shared hit=3304 read=170
                    ->  Bitmap Heap Scan on billing_events  (cost=164.50..6401.47 rows=5026 width=10) (actual time=2.040..13.250 rows=4975 loops=1)
                          Recheck Cond: ((account_id = '00000000-0000-0000-0000-000000000001'::uuid) AND (occurred_at >= '2026-08-30 13:52:35.008467+00'::timestamp with time zone) AND (occurred_at < '2026-09-29 13:52:35.008467+00'::timestamp with time zone))
                          Heap Blocks: exact=3446
                          Buffers: shared hit=3304 read=170
                          ->  Bitmap Index Scan on billing_events_account_occurred_idx  (cost=0.00..163.25 rows=5026 width=0) (actual time=1.339..1.339 rows=4975 loops=1)
                                Index Cond: ((account_id = '00000000-0000-0000-0000-000000000001'::uuid) AND (occurred_at >= '2026-08-30 13:52:35.008467+00'::timestamp with time zone) AND (occurred_at < '2026-09-29 13:52:35.008467+00'::timestamp with time zone))
                                Buffers: shared read=28
Planning:
  Buffers: shared hit=14 read=2
Planning Time: 0.587 ms
Execution Time: 18.549 ms
```

### Interpretation

- The query took 121.495 ms before and 18.549 ms after: an 84.7% reduction, or about 6.55× faster in this run. Shared buffers fell from 5,725 hits / 448 reads to 3,304 hits / 170 reads.
- The planner changed from a `Parallel Seq Scan` to a `Bitmap Index Scan` on `billing_events_account_occurred_idx` followed by a `Bitmap Heap Scan`. It read 4,975 matching rows instead of scanning the whole table for the account/time filter.
- The before-plan scan estimated 1,985 rows per worker and observed 1,658 per worker (about 19.7% high). The after-plan index scan estimated 5,026 rows and observed 4,975 (about 1.0% high). These are the EXPLAIN estimates for this one execution, not a general estimate-accuracy guarantee.
- The candidate indexes were `(account_id, occurred_at)` and `(account_id, occurred_at, endpoint) INCLUDE (duration_ms)`. Equality on account comes first, then the timestamp range; endpoint is behind the range as a grouping/coverage value, not a leading filter, and duration is included payload. The time-series plan selected the first index; it did not select the endpoint index. Both indexes were created inside the benchmark transaction, which rolled back afterward, so they are not retained in the database.

### Ingest p95 status: failed, not measured

`docker compose --profile tools run --rm ops-tools ingest_load.py` exited with code 1 and did not print a latency summary. The client raised `httpx.ReadError` during `POST /v1/usage`. In the ingest service logs, concurrent requests hit `asyncpg.exceptions.QueryCanceledError: canceling statement due to statement timeout` on the `INSERT ... ON CONFLICT ...` update of `ingest_rate_limits` for the same account. The ingest database connection config sets `statement_timeout` to 2,000 ms (`services/ingest/app/db.py`). The load tool defaults to 300 events at concurrency 20 for one account, so the upsert serializes on that account's rate-limit row; contention is the likely reason requests exceeded the database timeout. Because the command failed before its summary, no p95 value or <50 ms pass/fail result is available. This ingest-performance requirement remains unverified.
