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

## Stage 2a — snapshot at ≈75% (backend gaps + frontend core)

**Correctness bugs fixed**
- **3xx / 1xx were billed.** The billable filter was `status_code BETWEEN 200 AND 499`, which includes redirects. The brief says
  *only 2xx and 4xx* are billable. Fixed everywhere the predicate lives (hourly rollup, time series, period charges, what-if, seed,
  perf script). Regression tests: rollup, time series and invoice each assert that 1xx/3xx/5xx are never counted. The old seed and
  generator never emitted a 3xx, which is why nothing caught it.
- **Key rotation was invisible.** `GET /api-keys` did not return `overlap_expires_at`, so a key still valid during its rotation grace
  window looked "revoked". It is now returned.
- **`pytest-asyncio` was missing from ingest's requirements** although its tests are async.

**Tests added**
- `services/ingest/tests/test_http_api.py`: real FastAPI wiring with fakes, no DB needed — 202 accept, 401 bad key, 422 invalid
  payloads, and **429 with a `Retry-After` header** (previously only the limiter class was unit-tested).
- Frontend: 24 pure-logic tests (`npm test`) for money formatting, timezone handling, URL state, chart geometry, CSV export.

**Frontend rebuilt (was one 54-line dense file that called endpoints that do not exist)**
- **The old UI could not talk to the real backend**: it requested `/reports/usage/time-series` and `/reports/usage/mtd`; the API
  exposes `GET /reports/usage?report=time_series|mtd|p95|top_overage`.
- **Timezone bug**: the range pickers were seeded with `toISOString().slice(0,16)` (UTC wall time) but `datetime-local` reads local
  time, so every range was shifted by the viewer's UTC offset (5h30 in India). Now converted explicitly and covered by a test that
  runs in `Asia/Kolkata`.
- **Live ranges froze**: the end of the range was fixed at page load, so polling never showed new data. Presets (24h/7d/30d) now
  resolve "now" when each request runs; only *Custom* ranges are fixed.
- Split into `api/` (typed client, hooks), `lib/` (pure, tested), `hooks/`, `components/`. URL is the source of truth
  (`?view=&account=&g=&range=&start=&end=&q=&sort=&order=&page=`).
- Built in this snapshot: dashboard (zero-filled chart, range picker, hourly/daily toggle, MTD cards, p95, top-overage), account list
  (server-side pagination/search/sort), account detail (plan, allowance progress bar, projected overage, p95 per endpoint), token gate.
- Still to come in the final package: invoice preview/print, API-key management, plan comparison, docs polish, final verification.

## Stage 2b — final (≈100%)
_(added in the final package)_
