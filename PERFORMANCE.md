# Performance

This document covers two measurements:

1. The main reporting query (hourly, zero-filled usage time series) over 500,000 events: query, `EXPLAIN (ANALYZE, BUFFERS)` before and after indexing, index choice and planner behaviour.
2. The latest `POST /v1/usage` ingest benchmark against the assignment target of **p95 < 50 ms locally**.

---

# Part 1: Reporting-query performance

The dashboard time-series query filters `billing_events` by account and arbitrary timestamp bounds, groups billable statuses into hourly buckets, and left-joins a `generate_series` so empty buckets remain visible as zeros. It is benchmarked over a 30-day interval.

## Query

```sql
WITH buckets AS (
  SELECT generate_series(
    date_trunc('hour', $2::timestamptz),
    date_trunc('hour', $3::timestamptz - interval '1 microsecond'),
    interval '1 hour'
  ) AS bucket
),
usage AS (
  SELECT
    date_trunc('hour', occurred_at) AS bucket,
    count(*) FILTER (
      WHERE status_code BETWEEN 200 AND 299
         OR status_code BETWEEN 400 AND 499
    ) AS calls
  FROM billing_events
  WHERE account_id = $1::uuid
    AND occurred_at >= $2
    AND occurred_at < $3
  GROUP BY 1
)
SELECT
  buckets.bucket,
  COALESCE(usage.calls, 0)::bigint AS billable_calls
FROM buckets
LEFT JOIN usage USING (bucket)
ORDER BY buckets.bucket;
```

Reproduce:

```
docker compose --profile tools run --rm ops-tools performance.py
```

The script emits `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` before and after candidate index creation, inside a transaction that rolls back, so the schema is left unchanged. The "before" plan is measured with no candidate indexes present.

## Dataset and environment

- PostgreSQL 16.4, Docker Engine 29.8.1, Docker Compose 5.5.1
- Measured on 2026-09-29
- 505,000 attempted deliveries, 500,000 unique retained events, 50 accounts, 3 plans, 60 days of event times
- Benchmark account: `00000000-0000-0000-0000-000000000001`
- Interval: `2026-08-30 13:52:35.008467+00` to `2026-09-29 13:52:35.008467+00`
- Result: 721 hourly buckets

## EXPLAIN (ANALYZE, BUFFERS) before any index

PostgreSQL used a **Parallel Seq Scan**, reading the table and discarding every row outside the account and time range.

```
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

## Index added, and why

```sql
CREATE INDEX billing_events_account_occurred_idx
ON billing_events (account_id, occurred_at);
```

`account_id` is an equality predicate and `occurred_at` is a range predicate. Equality first lets the B-tree narrow to one account's contiguous slice, and the range column second turns the time filter into a bounded scan inside that slice. Reversing the order would scan the time range across all accounts and filter by account afterwards.

A second candidate, `(account_id, occurred_at, endpoint) INCLUDE (duration_ms)`, was evaluated for endpoint-latency queries. The planner did not choose it for this query, so it is dropped by migration `0002`. `endpoint` is not a leading filter here, and a wider index would only add write and storage cost.

## EXPLAIN (ANALYZE, BUFFERS) after the index

The planner changed from a Parallel Seq Scan to a **Bitmap Index Scan** on `billing_events_account_occurred_idx` followed by a **Bitmap Heap Scan**. A bitmap scan suits this query because it touches roughly 5,000 rows scattered across the heap.

```
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

## Improvement

| Metric | Before | After |
|---|---|---|
| Execution time | 121.495 ms | 18.549 ms |
| Planning time | 4.035 ms | 0.587 ms |
| Buffer hits | 5,725 | 3,304 |
| Buffer reads | 448 | 170 |
| Scan strategy | Parallel Seq Scan | Bitmap Index Scan + Bitmap Heap Scan |

Execution time dropped about **84.7%** (**6.55x faster**). The parallel workers and Gather node are no longer needed, because PostgreSQL reads only the matching account and time slice.

## Row-estimate accuracy

- Before: estimated 1,985 rows per worker, observed 1,658 (about 19.7% overestimate).
- After: estimated 5,026 rows, observed 4,975 (about 1.0% overestimate).

Estimates were close in both plans, so the plan change came from the available access path and not from a misestimate. The one visible miss is the `generate_series` branch (estimated 1,000 rows, actual 721), which is tiny and does not affect the plan. These figures describe this run only.

---

# Part 2: Ingest latency (`POST /v1/usage`)

**Target:** p95 < 50 ms locally, with every request accepted.

The ingest path validates the request, authenticates the API key, applies the per-account rate limit, then writes the usage event and its outbox row in one transaction and returns `202 Accepted`. No rating happens inline.

```
Request -> validate -> authenticate API key -> rate limit
        -> persist usage event + outbox message (one transaction)
        -> 202 Accepted
```

## Benchmark

`scripts/ingest_load.py` sends real `POST /v1/usage` requests: 10 warm-up requests (warming the HTTP connection, API-key cache and DB pool), then 120 measured requests at configurable concurrency. It validates HTTP statuses, reports p50, p95 and max, and fails if any request is rejected or p95 is not below 50 ms.

```
docker compose --profile tools run --rm ops-tools ingest_load.py
```

## Latest result

Configuration: `pool_pre_ping=False`, concurrency 4, 120 measured requests.

| Metric | Result |
|---|---|
| Accepted requests | 120 / 120 (HTTP 202) |
| p50 | 23.98 ms |
| p95 | **49.43 ms** |
| max | 100.61 ms |
| Target (p95 < 50 ms) | Met |

## What made it fast

With `pool_pre_ping=True`, SQLAlchemy issues an extra liveness round trip on every connection checkout. On a path whose whole job is one short transaction, that overhead was a large share of total latency. Setting `pool_pre_ping=False` removes it.

## Caveats

- **Thin margin.** 49.43 ms against a 50 ms target is a pass, but not a comfortable one. A single 120-request run on a local machine varies with Docker's VM, disk state and other load. Treat it as at the limit of the target.
- **Reliability trade-off.** The pool no longer detects silently dropped connections, so the first request on a stale connection can fail. This is mitigated by connection recycling and by client retries, which are safe because `event_id` makes ingest idempotent. In production I would keep pre-ping on and reduce latency another way (a pooler such as PgBouncer, or `pool_recycle` tuned below the server idle timeout).
- **Small sample.** With 120 requests, p95 is effectively the 6th-slowest request, so it is noisy. A longer run would be more trustworthy.

---

# Summary

| Measurement | Result |
|---|---|
| Reporting query, before index | 121.495 ms (Parallel Seq Scan) |
| Reporting query, after index | 18.549 ms (Bitmap Index Scan) |
| Reporting improvement | ~84.7% faster (6.55x) |
| Ingest p50, concurrency 4 | 23.98 ms |
| Ingest p95, concurrency 4 | 49.43 ms (target < 50 ms, met) |
| Ingest max, concurrency 4 | 100.61 ms |

# Reproducing

```
# Reporting query plans (rolls back, schema unchanged)
docker compose --profile tools run --rm ops-tools performance.py

# Ingest latency
docker compose --profile tools run --rm ops-tools ingest_load.py
```

Run the benchmarks against the local Docker Compose environment so the results reflect the real application, database, key cache, connection pool and network path. All numbers are specific to the submission machine.
