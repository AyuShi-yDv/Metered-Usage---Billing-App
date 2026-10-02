# Fullstack Assignment B — Metered API Usage & Billing
## Project Documentation / Submission Walkthrough

> This document explains the assignment, the implemented solution, where each requirement is handled, the engineering decisions, the frontend workflow, testing/benchmarking, and the remaining environment-dependent verification steps.

---

## 1. Assignment summary

The assignment is a  full-stack take-home project for a SaaS product that charges customers for API calls.

The product has two core needs:

1. Customers need a live usage dashboard.
2. Finance needs accurate monthly invoices.

The assignment evaluates four major areas:

- **React / TypeScript** — server state, forms and large tables.
- **Python / FastAPI** — layering, async behavior, validation and transactions.
- **PostgreSQL / SQL** — schema design, constraints and database-side reporting.
- **Microservices** — service boundaries, asynchronous communication and failure handling.

The brief intentionally contains more work than can always be completed perfectly in two weeks. It explicitly values completing and documenting the MUST requirements before optional STRETCH work.

---

## 2. Required technology stack

| Layer | Implementation |
|---|---|
| Frontend | React 18 + TypeScript + Vite |
| Server state | TanStack Query |
| Backend | Python 3.11+ + FastAPI |
| ORM | SQLAlchemy 2.x async |
| Validation | Pydantic v2 |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Messaging | RabbitMQ + transactional outbox |
| Services | `ingest-service` and `billing-service` |
| Deployment | Docker Compose |

The two backend services use separate PostgreSQL databases and do not share database tables.

---

## 3. High-level architecture

```text
                    ┌─────────────────────┐
                    │     React UI        │
                    │  TypeScript / Vite  │
                    └──────────┬──────────┘
                               │ HTTP
                               ▼
                    ┌─────────────────────┐
                    │   billing-service   │
                    │ reports / invoices  │
                    │ plans / account API │
                    └───────┬───────┬─────┘
                            │       │
                    PostgreSQL      │
                    billing DB      │
                                    │ RabbitMQ
                                    │ messages
                                    ▼
                    ┌─────────────────────┐
 API key + usage ──►│   ingest-service   │
                    │ validation / auth  │
                    │ event + outbox     │
                    └─────────┬───────────┘
                              │
                         PostgreSQL
                         ingest DB

                 ┌─────────────────────┐
                 │   Event Generator   │
                 │ duplicate / late /  │
                 │ out-of-order events │
                 └─────────────────────┘
```

### Why this boundary?

`ingest-service` is optimized for fast, write-heavy ingestion. It does not wait for billing calculations.

`billing-service` owns the financial model: plans, rollups, invoices and reporting.

RabbitMQ provides asynchronous delivery. The transactional outbox ensures the usage event and its outgoing message are committed together.

---

## 4. What was implemented

### 4.1 Usage ingestion

**Location:**

- `services/ingest/app/main.py`
- `services/ingest/app/auth.py`
- `services/ingest/app/repository.py`
- `services/ingest/app/outbox.py`
- `services/ingest/app/ratelimit.py`

The `POST /v1/usage` endpoint:

- authenticates with an API key;
- validates the request with Pydantic;
- stores the usage event;
- writes an outbox message in the same transaction;
- returns without performing inline billing/rating;
- enforces event idempotency using the database.

Only one copy of a repeated `event_id` becomes billable.

---

### 4.2 Asynchronous billing

**Location:**

- `services/billing/app/consumer.py`
- `services/billing/app/worker.py`
- `services/ingest/app/outbox.py`
- `compose.yaml`

Usage events are transferred asynchronously through RabbitMQ.

The consumer uses retries and dead-letter handling so a temporary billing failure does not force the ingest endpoint to perform billing synchronously.

---

### 4.3 Hourly rollups and concurrency

**Location:**

- `services/billing/app/worker.py`
- `services/billing/tests/test_rollup_postgres.py`

Hourly usage is aggregated from canonical events.

The implementation is designed so rerunning a rollup does not increment an existing value again. Concurrency controls prevent two workers processing the same hour from double counting.

Tests explicitly exercise concurrent processing.

---

### 4.4 Money and invoice calculation

**Location:**

- `services/billing/app/money.py`
- `services/billing/app/charges.py`
- `services/billing/app/invoices.py`

Money is stored as integer cents.

The invoice consists of:

- base fee;
- billable included usage;
- overage calls;
- overage charge;
- invoice line items;
- applicable late-event adjustments.

Half-up rounding is performed at the invoice level rather than independently per event.

---

### 4.5 Late and already-invoiced events

Usage events can arrive after their event timestamp. Billing uses the event timestamp to determine the correct billing period rather than simply using arrival time.

If an already-invoiced period receives a valid late event, the solution records an adjustment that can be represented in the next billing workflow. The rationale and failure behavior are documented in `DECISIONS.md`.

---

## 5. SQL reporting implementation

**Main location:** `services/billing/app/reports.py`

The assignment specifically requires reporting to be calculated in PostgreSQL rather than by pulling large datasets into Python.

Implemented reports include:

### Usage time series

- hourly or daily buckets;
- arbitrary date range;
- zero-filled gaps;
- PostgreSQL `generate_series`;
- `LEFT JOIN` against usage data.

### p95 latency

Endpoint latency uses PostgreSQL `percentile_cont` directly in SQL.

### Month-to-date billing

The report calculates:

- billable calls;
- included allowance;
- current overage;
- projected end-of-month overage;
- projected overage cost.

### Top overage accounts

The query uses a window function (`DENSE_RANK`) and calculates month-over-month change.

### Query count

The report routes are deliberately structured around one SQL statement per report and do not use Python aggregation loops or N+1 database calls.

---

## 6. Frontend / GUI

The final UI has been upgraded into a polished finance/billing console rather than a plain collection of forms.

### Visual system

- dark professional operations-console theme;
- cyan/blue accent system;
- responsive desktop sidebar;
- mobile navigation drawer;
- glass-style panels;
- clear typography hierarchy;
- status indicators;
- responsive tables and cards;
- accessible focus states;
- print-friendly invoice styling.

### Main navigation

The application contains:

1. **Overview**
2. **Accounts**
3. **Invoices**
4. **API keys**
5. **Plans**

### Overview dashboard

**Location:** `frontend/src/components/Dashboard.tsx`

Displays:

- calls this month;
- percentage of allowance used;
- overage calls;
- projected month-end overage;
- projected overage cost;
- usage time-series chart;
- hourly/daily controls;
- date-range controls;
- p95 latency table;
- top overage accounts;
- live refresh status.

The URL reflects the selected account, date range and granularity.

### Accounts

**Location:** `frontend/src/components/AccountsTable.tsx`

Provides:

- server-side pagination;
- search;
- sorting;
- plan information;
- usage totals.

Account details show:

- current plan;
- allowance consumption;
- projected overage;
- endpoint-level p95 latency;
- plan pricing information.

### Invoices

**Location:** `frontend/src/components/Invoices.tsx`

Provides:

- billing-period selector;
- invoice preview;
- line items;
- base fee;
- overage fee;
- total;
- pending adjustments;
- finalize action;
- printable / Save as PDF workflow;
- finalized invoice history.

### API keys

**Location:** `frontend/src/components/ApiKeys.tsx`

Provides:

- create key;
- list keys;
- revoke key;
- rotate key;
- one-time secret display;
- rotation-overlap information.

The secret is intentionally shown only when it is created or rotated.

### Plans

**Location:** `frontend/src/components/Plans.tsx`

Provides:

- current plan information;
- alternative plan comparison;
- what-if cost calculation;
- difference in projected cost;
- effective-dated plan change scheduling.

This completes the frontend for the STRETCH what-if feature as well.

---

## 7. API key security model

API secrets are generated using secure randomness.

The database stores a digest rather than the plaintext secret.

The UI receives the plaintext secret only at creation/rotation time so the user can copy it. Subsequent list operations only expose safe metadata such as:

- key ID;
- prefix;
- created timestamp;
- revoked timestamp;
- overlap expiry.

---

## 8. Rate limiting and resilience

The ingest service implements per-account rate limiting.

When the limit is exceeded:

- HTTP `429` is returned;
- `Retry-After` is included.

Because billing is asynchronous, the ingest path can continue accepting valid events while billing catches up or retries failed messages.

RabbitMQ retry/delay handling eventually moves unrecoverable messages to a dead-letter path.

---

## 9. Database design principles

The project follows these rules from the assignment:

- integer cents for money;
- UTC timestamps;
- database-enforced uniqueness for event IDs;
- separate databases for the two services;
- Alembic migrations instead of `create_all()`;
- constraints used to enforce important invariants;
- reporting work performed in SQL.

---

## 10. Testing

The repository contains:

### Ingest tests

`services/ingest/tests/`

Coverage includes authentication, HTTP behavior, idempotency, concurrency and rate limiting.

### Billing tests

`services/billing/tests/`

Coverage includes:

- money arithmetic;
- invoice calculations;
- idempotent event handling;
- rollups;
- concurrent rollups;
- SQL reports;
- plan changes;
- what-if calculations.

### Frontend tests

`frontend/src/lib/*.test.ts`

Utility tests cover money, period, chart, URL and time behavior.

---

## 11. Performance work

**Location:** `PERFORMANCE.md`

The reporting benchmark uses a 500,000-event dataset.

The documented reporting query was measured before and after indexes. The repository records the SQL query, EXPLAIN output, index reasoning, planner behavior and wall-clock improvement.

### Ingest benchmark

**Location:** `scripts/ingest_load.py`

The benchmark was improved to:

1. warm up the HTTP/API-key/database path;
2. run controlled concurrency;
3. collect successful response timings;
4. report p50, p95 and maximum latency;
5. fail the benchmark if requests are unsuccessful;
6. explicitly require p95 below 50 ms.

The final p95 number must be generated on the target Docker environment because network/database performance is environment-dependent. The benchmark does not claim a passing result without actually measuring one.

---

## 12. Docker / startup workflow

The intended clean-clone workflow is:

```bash
cp .env.example .env
docker compose up --build
```

Then open:

```text
http://localhost:5173
```

The Compose stack contains the application services, PostgreSQL databases, RabbitMQ, frontend and generator/tooling containers.

For the large benchmark dataset:

```bash
docker compose --profile tools run --rm ops-tools seed.py
```

For reporting performance:

```bash
docker compose --profile tools run --rm ops-tools performance.py
```

For ingest latency:

```bash
docker compose --profile tools run --rm ops-tools ingest_load.py
```

---

## 13. Required live-environment validation

Before submitting the repository, run the following in an environment with Docker installed:

```bash
docker compose up --build
```

Then run:

```bash
docker compose --profile tests run --rm ingest-tests
docker compose --profile tests run --rm billing-tests
```

Then create the large dataset and run:

```bash
docker compose --profile tools run --rm ops-tools seed.py
docker compose --profile tools run --rm ops-tools performance.py
docker compose --profile tools run --rm ops-tools ingest_load.py
```

Finally verify the frontend build:

```bash
cd frontend
npm ci
npm run check
npm run build
```

The benchmark and build should be considered final evidence only after these commands complete successfully on the target machine.

---

## 14. Important engineering decisions

The repository's `DECISIONS.md` contains the concise review-session version of these decisions.

The key decisions are:

- separate ingestion and billing responsibilities;
- asynchronous event handoff;
- transactional outbox for reliable publication;
- database uniqueness for idempotency;
- canonical-event recomputation for safe rollups;
- SQL-first reporting for large datasets;
- integer money representation;
- effective-dated plan history;
- retry/dead-letter handling for distributed failures.

---

## 15. Where to find the important work

| Area | Main files/directories |
|---|---|
| Ingest API | `services/ingest/app/main.py` |
| Ingest auth | `services/ingest/app/auth.py` |
| Ingest persistence | `services/ingest/app/repository.py` |
| Outbox | `services/ingest/app/outbox.py` |
| Rate limiting | `services/ingest/app/ratelimit.py` |
| Billing consumer | `services/billing/app/consumer.py` |
| Rollups | `services/billing/app/worker.py` |
| Invoices | `services/billing/app/invoices.py` |
| Money | `services/billing/app/money.py` |
| Billing rules | `services/billing/app/charges.py` |
| SQL reports | `services/billing/app/reports.py` |
| Billing routes | `services/billing/app/routers/` |
| React shell | `frontend/src/App.tsx` |
| Dashboard | `frontend/src/components/Dashboard.tsx` |
| Accounts | `frontend/src/components/AccountsTable.tsx` |
| Account detail | `frontend/src/components/AccountDetail.tsx` |
| Invoice UI | `frontend/src/components/Invoices.tsx` |
| API-key UI | `frontend/src/components/ApiKeys.tsx` |
| Plan UI | `frontend/src/components/Plans.tsx` |
| Shared UI | `frontend/src/components/ui.tsx` |
| SQL performance | `PERFORMANCE.md` |
| Design decisions | `DECISIONS.md` |
| Final validation | `FINAL_VALIDATION.md` |
| This documentation | `docs/PROJECT_DOCUMENTATION.md` |

---

## 16. Assignment-to-solution checklist

### MUST

- [x] Usage ingestion endpoint
- [x] API-key authentication
- [x] Async handoff
- [x] Idempotent events
- [x] Safe hourly rollups
- [x] Concurrent rollup protection
- [x] Invoice generation
- [x] SQL time series
- [x] Zero-filled reporting
- [~] SQL p95 latency
- [x] MTD usage and projected overage
- [x] Top-overage ranking
- [x] Server-side account table
- [x] Account detail
- [x] Usage dashboard
- [x] Invoice frontend
- [x] API-key frontend

### SHOULD

- [x] API-key rotation
- [x] Rate limiting
- [x] Retry-After
- [x] Backpressure/retry/DLQ
- [x] Live dashboard refresh
- [x] Distinct loading/empty/error states

### STRETCH

- [x] Mid-month plan changes
- [x] Proration
- [x] What-if endpoint
- [x] Plan comparison UI

---

## 17. Final submission notes

This repository is designed to be explainable during the live review. The candidate should be able to explain:

1. why the service boundary exists;
2. why ingest does not perform billing synchronously;
3. how duplicate messages are prevented from inflating invoices;
4. how rollups remain safe under retries/concurrency;
5. how reporting stays inside PostgreSQL;
6. how money and rounding are represented;
7. how API secrets are handled;
8. how the UI maps to the billing APIs;
9. what happens when RabbitMQ or billing is temporarily unavailable;
10. what performance bottlenecks are expected at significantly larger data volumes.

The assignment explicitly allows AI assistance, but the submitted code must be understandable by the person presenting it during the live review.

---

## 18. Submission inventory

The final archive contains the original application structure plus:

- upgraded responsive GUI;
- completed invoice screen;
- completed API-key management screen;
- completed plan-comparison screen;
- improved visual system/navigation;
- project documentation in `docs/PROJECT_DOCUMENTATION.md`;
- performance and decision documents;
- validation scripts;
- Git history.

Exact runtime performance and Docker startup evidence should be captured on the final submission machine because those measurements depend on the local Docker/CPU/database environment.
