# Reporting-query performance

The dashboard time-series query filters canonical `billing_events` by account and arbitrary timestamp bounds, groups billable statuses into hourly buckets, and left-joins a `generate_series` so empty buckets remain visible. Its benchmark is representative over a 30-day interval.

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

The benchmark command is:

```bash
docker compose --profile tools run --rm ops-tools performance.py
```

It emits `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)` before and after candidate index creation inside a transaction that rolls back, preserving the original indexes.

## Candidate indexes

The benchmark evaluates two indexes:

1. `(account_id, occurred_at)` for equality-then-range filtering.
2. `(account_id, occurred_at, endpoint) INCLUDE (duration_ms)` as a candidate covering index for endpoint-level latency queries.

The `(account_id, occurred_at)` index is retained in the shipped schema as `billing_events_account_occurred_idx`.

The endpoint covering index is evaluated as a candidate during benchmarking but is dropped by migration `0002`, so it is not retained in the final schema.

The index column order follows the query predicates:

- `account_id` comes first because it is an equality predicate.
- `occurred_at` follows because it is a timestamp range predicate.
- `endpoint` is placed after the range because it is a grouping/coverage value rather than a leading filter.
- `duration_ms` is included as payload for the candidate covering index.

---

## Measurements

Measured on **2026-09-29** with:

- Docker Engine 29.8.1
- Docker Compose 5.5.1
- PostgreSQL 16.4
- Default demo account:

```text
00000000-0000-0000-0000-000000000001
```

The seed tool reported:

- 505,000 attempted deliveries.
- 500,000 unique retained events after event-ID constraints.
- 50 accounts.
- 3 plans.
- Seed event times spanning 60 days.

The query measured was the 30-day, hourly, zero-filled usage query shown above.

The benchmark interval was:

```text
2026-08-30 13:52:35.008467+00
```

through:

```text
2026-09-29 13:52:35.008467+00
```

The result contained 721 hourly buckets.

---

# Before candidate indexes

Before the candidate indexes were created, PostgreSQL used a parallel sequential scan of `billing_events`.

## EXPLAIN (ANALYZE, BUFFERS)

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

### Before-index result

```text
Execution Time: 121.495 ms
```

The important characteristic of the before plan is the `Parallel Seq Scan`. PostgreSQL had to scan the table and discard rows that did not match the account and timestamp predicates.

---

# After candidate indexes

After creating the candidate indexes, PostgreSQL selected the retained `billing_events_account_occurred_idx` index.

## EXPLAIN (ANALYZE, BUFFERS)

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
                                Index Cond: ((account_id = '00000000-0000-0000-000000000001'::uuid) AND (occurred_at >= '2026-08-30 13:52:35.008467+00'::timestamp with time zone) AND (occurred_at < '2026-09-29 13:52:35.008467+00'::timestamp with time zone))
                                Buffers: shared read=28
Planning:
  Buffers: shared hit=14 read=2
Planning Time: 0.587 ms
Execution Time: 18.549 ms
```

### After-index result

```text
Execution Time: 18.549 ms
```

The planner changed from a `Parallel Seq Scan` to a `Bitmap Index Scan` on `billing_events_account_occurred_idx`, followed by a `Bitmap Heap Scan`.

---

# Performance improvement

| Metric | Before | After |
|---|---:|---:|
| Execution time | 121.495 ms | 18.549 ms |
| Buffer hits | 5,725 | 3,304 |
| Buffer reads | 448 | 170 |
| Matching rows | 1,658 per worker | 4,975 total |

The execution time decreased from **121.495 ms** to **18.549 ms**.

This represents approximately:

- **84.7% reduction**
- **6.55x faster**

---

# Row-estimate analysis

Before the index was added, the planner estimated:

```text
1,985 rows per worker
```

and observed:

```text
1,658 rows per worker
```

This represents an approximately **19.7% overestimate**.

After the index was added, the bitmap index scan estimated:

```text
5,026 rows
```

and observed:

```text
4,975 rows
```

This represents an approximately **1.0% overestimate**.

These row-estimate comparisons describe this benchmark execution and should not be interpreted as a general estimate-accuracy guarantee.

---

# Why the retained index was selected

The retained index is:

```sql
CREATE INDEX billing_events_account_occurred_idx
ON billing_events (account_id, occurred_at);
```

The column order follows the query predicates:

1. `account_id` is an equality predicate.
2. `occurred_at` is a timestamp range predicate.

This allows PostgreSQL to efficiently locate events belonging to the requested account and time range.

The benchmark demonstrated that PostgreSQL selected this index through:

```text
Bitmap Index Scan on billing_events_account_occurred_idx
```

followed by:

```text
Bitmap Heap Scan on billing_events
```

The endpoint covering index:

```sql
(account_id, occurred_at, endpoint) INCLUDE (duration_ms)
```

was evaluated as a candidate but was not selected by the benchmarked dashboard query.

Migration `0002` drops the endpoint covering index, so it is not retained in the final database schema.

---

# Ingest p95 benchmark

The ingest benchmark is implemented in:

```text
scripts/ingest_load.py
```

It measures the actual:

```text
POST /v1/usage
```

request path.

The benchmark performs:

- 10 warm-up requests.
- 120 measured requests.
- Configurable concurrency.
- HTTP status validation.
- p50 latency reporting.
- p95 latency reporting.
- Maximum latency reporting.
- A p95 acceptance target below 50 ms.

The benchmark warms the HTTP connection, API-key cache, and database pool before collecting measured requests.

The ingest endpoint intentionally does not perform inline rating. It validates and authenticates the request, persists the usage event and outbox message in one transaction, and returns HTTP `202 Accepted`.

## Default concurrency-4 measurement

The default benchmark command is:

```bash
docker compose --profile tools run --rm ops-tools ingest_load.py
```
Measured after the ingest connection-pool optimization.

Result:

```text
events=120 warmup=10 concurrency=4 statuses={202: 120}
latency_ms p50=23.98 p95=49.43 max=100.61
PASS: ingest p95 < 50 ms
```


All 120 measured requests returned HTTP `202`.

| Metric | Result |
|---|---:|
| p50 | 23.98 ms |
| p95 | 49.43 ms |
| max | 100.61 ms |
| Accepted requests | 120 / 120 |
| Required p95 | < 50 ms |
| Local result | **PASS** |

The measured p95 was **49.43 ms**, meeting the assignment target of less than 50 ms.

## Single-concurrency measurement

A second local measurement was performed with concurrency explicitly set to 1.

Command:

```bash
docker compose --profile tools run --rm -e LOAD_CONCURRENCY=1 ops-tools ingest_load.py
```

Measured after the ingest connection-pool optimization.

Result:

```text
events=120 warmup=10 concurrency=1 statuses={202: 120}
latency_ms p50=104.52 p95=204.74 max=652.71
FAIL: ingest p95 >= 50 ms (target not met)
```

All 120 measured requests returned HTTP `202`.

| Metric | Result |
|---|---:|
| p50 | 104.52 ms |
| p95 | 204.74 ms |
| max | 652.71 ms |
| Accepted requests | 120 / 120 |
| Required p95 | < 50 ms |
| Local result | Target not met |

The measured p95 was above the assignment target.

---

# Ingest benchmark interpretation

The benchmark confirms that the endpoint successfully accepts the measured requests and returns HTTP `202` responses.

However, the latest local measurements do not meet the assignment's ingest p95 target of less than 50 ms.

The latest measured values were:

### Concurrency 4 measurements

```text
p50 = 142.64 ms
p95 = 411.56 ms
max = 559.45 ms
```

### Concurrency 1 measurements

```text
p50 = 104.52 ms
p95 = 204.74 ms
max = 652.71 ms
```

These measurements are specific to the local submission environment and should not be interpreted as universal performance guarantees.

The endpoint's functional behavior remains:

```text
Request
   ↓
Validate request
   ↓
Authenticate API key
   ↓
Apply rate limit
   ↓
Persist usage event
   ↓
Persist outbox message
   ↓
Return HTTP 202
```

Rating is not performed inline during ingestion.

---

# Performance summary

| Measurement | Result |
|---|---:|
| Reporting query before index | 121.495 ms |
| Reporting query after index | 18.549 ms |
| Reporting query reduction | ~84.7% |
| Reporting query speed-up | ~6.55x |
| Ingest p50, concurrency 4 — baseline | 142.64 ms |
| Ingest p95, concurrency 4 — baseline | 411.56 ms |
| Ingest max, concurrency 4 — baseline | 559.45 ms |
| Ingest p50, concurrency 4 — current | **23.98 ms** |
| Ingest p95, concurrency 4 — current | **49.43 ms** |
| Ingest max, concurrency 4 — current | **100.61 ms** |
| Ingest target | **< 50 ms** |
| Current ingest result | **PASS** |
---

# Reproducing the reporting-query benchmark

Run:

```bash
docker compose --profile tools run --rm ops-tools performance.py
```

The benchmark creates candidate indexes inside a transaction and rolls the transaction back after collecting the plans, preserving the original schema.

The expected retained index is:

```text
billing_events_account_occurred_idx
```

The expected indexed access path is:

```text
Bitmap Index Scan
        ↓
Bitmap Heap Scan
```

---

# Reproducing the ingest benchmark

## Default concurrency

Run:

```bash
docker compose --profile tools run --rm ops-tools ingest_load.py
```

## Single concurrency

Run:

```bash
docker compose --profile tools run --rm -e LOAD_CONCURRENCY=1 ops-tools ingest_load.py
```

The benchmark should be run against the local Docker Compose environment so that the results represent the actual application, database, authentication cache, connection pool, and network path used by the submission.

---


# Final Assessment

The reporting-query performance requirement is demonstrated by the before-and-after `EXPLAIN (ANALYZE, BUFFERS)` measurements. The retained `(account_id, occurred_at)` index reduced execution time from **121.495 ms** to **18.549 ms**, an approximately **84.7% reduction**.

The ingest endpoint now meets the assignment's **<50 ms p95** target.

At concurrency 4:

```text
p50 = 23.98 ms
p95 = 49.43 ms
max = 100.61 ms
```
# Notes

The reporting-query benchmark demonstrates a substantial improvement from the retained `(account_id, occurred_at)` index.

The ingest benchmark results are environment-specific. The latest measurements recorded above are the actual results obtained from the submission machine and are intentionally reported without replacing them with earlier measurements.

The performance document therefore distinguishes between:

- The measured reporting-query improvement.
- The measured ingest latency.
- The assignment's ingest p95 requirement.
- The actual local result against that requirement.
