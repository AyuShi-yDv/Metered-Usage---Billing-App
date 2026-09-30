# Review fixes (gap analysis against the assignment brief)

## Stage 1 — backend, data, infrastructure (≈60%)

**Correctness bugs fixed**
- **Money: double rounding in SQL.** `((x*price + 500) / 1000)::bigint` rounds twice (numeric division, then the cast), overstating
  projected overage / top-overage by ~1 cent. Now a single `round(x*price/1000)` (reports, account detail). Regression test added.
- **Possible event loss at startup.** Ingest published to a fanout exchange with no bound queue (RabbitMQ drops such messages) and
  marked them published. Ingest now declares the durable queue too (`shared-contracts/README.md`).
- **Duplicate publishers.** Every uvicorn worker ran an outbox loop with no row locking. Rows are now claimed with
  `FOR UPDATE SKIP LOCKED`; failures are recorded in `last_error`; published rows are purged after 7 days.
- **Rate limiter.** Was per-process ×4 workers (limit effectively 4×) with a misleading "sliding window" comment. Now an exact fixed-window
  limiter (one worker by default), configurable, unit-tested, `Retry-After` computed correctly.
- **Revocation lag.** Key cache TTL 60 s → 5 s (configurable); misses are cached briefly so random prefixes cannot hammer the DB.
- **Clock skew.** Timestamps up to 5 min in the future are accepted (a slightly fast client clock no longer gets 422).
- **Top-overage report** returned *every* account with zero overage tied at rank 1; now only accounts with overage > 0.
- **Unbounded `generate_series`.** Time-series range is capped (92 days hourly / 1100 days daily) → 422.
- **Bucketing on UTC.** Both services pin the session `timezone=UTC`.
- **Token comparison** is bytes-safe (non-ASCII tokens previously caused a 500).
- **Seed data had nobody in overage**, making overage reports empty; seed is now Zipf-skewed, runs automatically in `docker compose up`.
- **Invoice line items** were two lines with `quantity=1`; now usage / base fee / overage lines with real quantities that sum to the total.
- **Dropped the redundant `(account_id, occurred_at, endpoint) INCLUDE (duration_ms)` index** (never chosen by the planner; slows ingest writes).
- Removed `synchronous_commit=off` from ingest's database (accepted events must be durable).
- Unused `ingest_rate_limits` table dropped (migration 0002).

**Structure (Python / FastAPI layering)**
`billing/app/main.py` (364 dense lines: routes + SQL + invoices + consumer) → `routers/` (reports, accounts, invoices, keys),
`invoices.py` (service), `consumer.py`, `worker.py`, `ingest_client.py`, `deps.py`, `bootstrap.py`.
Ingest: `auth.py`, `ratelimit.py`, `repository.py`, `outbox.py`.

**Tests** now exercise real code paths instead of matching SQL strings or re-typing SQL: `store_event` ×5 (sequential and concurrent),
outbox claim disjointness, rollup re-run + concurrent rollup, consumer duplicates, report SQL executed against rows (zero-fill, p95,
MTD, DENSE_RANK + month-over-month), invoice exactly-once under concurrent finalize, late-event adjustment, proration.

## Stage 2 — frontend, docs, final verification (≈100%)
_(added in the final package)_
