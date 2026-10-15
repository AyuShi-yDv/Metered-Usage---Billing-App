

# Metered Usage & Billing App

A billing backend and dashboard for a SaaS product that charges per API call. Customers send usage events, the system counts them exactly once (even when events arrive twice or late), and finance gets usage reports and monthly invoices.

**Stack:** React 18 + TypeScript + Vite · FastAPI + SQLAlchemy 2 (async) · PostgreSQL 16 · RabbitMQ · Docker Compose

---

## 🚀 Live Demo


| Live URL | Link |
|---|---|
| Dashboard (frontend) | https://imaginative-cooperation-production-dd42.up.railway.app/ |
| Billing API docs (Swagger) | https://intelligent-stillness-production-0dc4.up.railway.app/docs |
| Ingest API docs (Swagger) | https://metered-usage-billing-app-production-e8d5.up.railway.app/docs |

---

## Quick start

**You need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running) and Git. Nothing else.

Free ports required: `5173`, `8000`, `8001`, `5672`, `15672`.

**1. Get the code**

```bash
git clone https://github.com/AyuShi-yDv/Metered-Usage---Billing-App.git
cd Metered-Usage---Billing-App
```

**2. Start everything**

```bash
docker compose up --build
```

**3. Wait for the banner.** The first start may take a few minutes: it builds the images, creates the databases and loads 500,000 sample usage events. When everything is ready, the terminal prints:

```text
ALL SERVICES ARE READY. Click a link to open it:
  App (frontend):      http://localhost:5173
  ...
```

**4. Open the app** at http://localhost:5173 (Ctrl/Cmd + click the link in the terminal).

**Sign in:** the dashboard asks for a token.

- Finance (all accounts): `demo-dashboard-token`
- Single account: a token mapped to that account in `ACCOUNT_DASHBOARD_TOKENS` (see Configuration). Without it, the account list is hidden.

| What | URL |
|---|---|
| Web app | http://localhost:5173 |
| Ingest API docs (Swagger) | http://localhost:8000/docs |
| Billing API docs (Swagger) | http://localhost:8001/docs |
| RabbitMQ dashboard | http://localhost:15672 (user `app`, password `app`) |

Missed the banner? Run `docker compose logs ready-banner`.

---

## 5-minute tour

1. **Dashboard** (home page): change the date range and the hourly/daily toggle. The URL updates, so you can share or reload the exact view. Quiet hours show as zero, not as gaps.
2. **Accounts**: search, sort by usage and page through the list. Open one to see its plan, allowance progress bar, projected overage cost and p95 latency per endpoint.
3. **Invoices**: pick an account and period to preview line items (base fee, overage, adjustments), then print or save as PDF.
4. **API keys**: create a key. The secret is shown **once** and cannot be retrieved again. You can also rotate and revoke keys.
5. **Try duplicate protection**: open http://localhost:8000/docs, expand `POST /v1/usage`, click *Try it out*, use your new key and a fresh UUID as `event_id`, then execute it **5 times** with the same body. The account's usage increases by **1**, not 5.

6. **Watch it live**: a generator sends events continuously (default 4 per second), including deliberate duplicates and late or out-of-order events. Dashboard numbers update without a page reload.

---

## 🏗️ Architecture

```text
              ┌───────────────────┐           ┌───────────────────┐
              │  Usage Generator  │           │  React Frontend   │
              │ duplicates / late │           │ TypeScript + Vite │
              │  / out-of-order   │           │       :5173       │
              └─────────┬─────────┘           └─────────┬─────────┘
                        │ POST /v1/usage                │ HTTP / REST
                        ▼                               ▼
              ┌───────────────────┐           ┌───────────────────┐
              │  Ingest Service   │           │  Billing Service  │
              │   FastAPI :8000   │           │   FastAPI :8001   │
              │                   │           │                   │
              │ API Key Auth      │           │ Plans             │
              │ Validation        │           │ Rollups           │
              │ Idempotency       │           │ Rating            │
              │ Rate Limiting     │           │ Invoices          │
              └─────────┬─────────┘           │ Reports           │
                        │ one transaction     └─────────┬─────────┘
                        ▼                               │
              ┌───────────────────┐                     │
              │     Ingest DB     │                     │
              │   PostgreSQL 16   │                     │
              └─────────┬─────────┘                     │
                        │ outbox publisher              │
                        ▼                               │
              ┌───────────────────┐                     │
              │     RabbitMQ      │                     │
              │  usage.accepted   │                     │
              └─────────┬─────────┘                     │
                        │                               │
                        ▼                               ▼
              ┌───────────────────┐           ┌───────────────────┐
              │  Billing Service  │           │    Billing DB     │
              │  Event Consumer   ├──────────►│   PostgreSQL 16   │
              └───────────────────┘           └───────────────────┘
```

- **Ingest service** authenticates the API key, validates the event, applies the rate limit, and stores the event plus an outbox row in **one transaction**. It returns `202 Accepted` and never calculates prices.
- **Billing service** consumes events from RabbitMQ, builds hourly rollups, rates usage against each account's plan, and produces invoices and reports.
- The two services are **separate processes with separate databases**. They never read each other's tables. They communicate only through RabbitMQ messages and HTTP.
- The browser talks to the billing service only. API-key actions are forwarded by billing to an internal ingest listener that is not exposed outside Docker.

## Key rules

| Rule | How it is handled |
|---|---|
| A duplicate `event_id` counts once, ever | Unique constraint on `event_id` in **both** databases: one stops repeated HTTP calls, the other stops repeated broker deliveries |
| Only 2xx and 4xx responses are billed | 5xx events are stored but never counted |
| Money | Integer cents everywhere, never floats. Rounded half-up at invoice level only |
| Time | Stored as `timestamptz` in UTC, shown in the user's local timezone |
| Reports | Computed in SQL (`generate_series` + `LEFT JOIN` for zero-filled series, `percentile_cont` for p95, `RANK()` for top accounts), never by looping in Python |
| Late events | A month closes 48 hours after it ends. A later event does not change a finalized invoice: it becomes an adjustment on the next invoice (details in `DECISIONS.md`) |

Example usage event (`POST /v1/usage`):

```json
{
  "event_id": "3f2b8c1e-9a4d-4e57-b6a1-0c7d5e8f2a10",
  "api_key": "<your-api-key>",
  "endpoint": "/v1/users",
  "timestamp": "<a UTC time from the last 24 hours, e.g. 2026-10-15T09:00:00Z>",
  "duration_ms": 142,
  "status_code": 200
}
```


> **Note:** `timestamp` must be within the last 24 hours (and no more than 5 minutes in the future), or ingest rejects the event.

---

## Run the tests

Backend:

```bash
docker compose --profile tests run --rm ingest-tests
docker compose --profile tests run --rm billing-tests
```


Frontend (needs Node.js 22+ on your machine, or run them in Docker):

```bash
cd frontend
npm install
npm run check
```

Each backend command ends with a summary like `N passed`. The backend tests cover money arithmetic, duplicate-event idempotency, concurrent rollup workers, billing calculations and the reporting SQL. The frontend tests cover the money, time, period and URL helpers, plus the API key secret display.

---

## Configuration

Defaults work out of the box. To change one, set it before starting, for example `SEED_EVENTS=0 docker compose up --build`.

| Variable | Default | Meaning |
|---|---|---|
| `SEED_EVENTS` | `500000` | Sample events to load (`0` skips seeding) |
| `EVENTS_PER_SECOND` | `4` | Live traffic rate from the generator |
| `RATE_LIMIT_PER_MINUTE` | `600` | Per-account limit on ingest (returns `429` with `Retry-After`) |
| `INGEST_WORKERS` | `1` | Number of ingest worker processes |
<!-- CHANGE: Added the five variables below. They were missing from the table. -->
| `DASHBOARD_TOKEN` | `demo-dashboard-token` | Finance login token (sees all accounts) |
| `ACCOUNT_DASHBOARD_TOKENS` | empty | JSON object mapping account IDs to single-account tokens, e.g. `{"<account-uuid>": "<token>"}` |
| `INTERNAL_TOKEN` | `change-me-in-production` | Shared secret between billing and ingest's private key-management listener |
| `INGEST_DB_PASSWORD` | `ingest-local-password` | Password for the ingest database app role |
| `BILLING_DB_PASSWORD` | `billing-local-password` | Password for the billing database app role |


> **Security:** every default token and password above is for local evaluation only. Change them before any deployment.

---

## Documentation

- [`DECISIONS.md`](DECISIONS.md): service boundary, outage behaviour, exactly-once handling, what I would change, what breaks at 100x data, late events after invoicing
- [`PERFORMANCE.md`](PERFORMANCE.md): the main reporting query, `EXPLAIN (ANALYZE, BUFFERS)` before and after indexing, index choice, and ingest latency measurements

## Known limitations

This project does not do everything perfectly. Here is what is incomplete:

- **Ingest latency:** the latest local benchmark measured p95 at **49.43 ms with concurrency 4**, just under the assignment's **<50 ms** target. This is a single local result, not a production guarantee (see `PERFORMANCE.md`).

- **Stale dashboard when billing is down:** events queue safely, but the dashboard shows stale numbers. There is no "data is stale" indicator and no dead-letter replay screen yet.

- **Rate limiting is per process:** the limiter keeps its counters in memory, so with `INGEST_WORKERS` above 1 each worker enforces the limit separately. Run one ingest worker, or move the counters to Postgres or Redis.

- **Key revocation has a short delay:** ingest caches key lookups for 5 seconds, so a revoked key can still be accepted for up to that long.

- **Rollups run per event:** each accepted event rebuilds its account-hour rollup. This is correct and idempotent but scales with event rate. See `DECISIONS.md` section 4 for the planned scheduled job.
- **Demo authentication:** the demo tokens above are static. A real deployment needs a proper identity provider and a secrets manager.
- **Local evaluation only:** Docker Compose is set up for local evaluation, not for production deployment.


---

## Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` | Another program uses that port. Close it, or change the left-hand number in the `ports:` line of `compose.yaml` |
| `Cannot connect to the Docker daemon` | Start Docker Desktop and wait until it says it is running |
| Banner never appears | Run `docker compose ps -a`, then `docker compose logs <service>` for any service that is restarting or exited with an error |
| App opens but looks empty | Seed data may still be loading. Wait for the banner, then refresh |
| Dashboard rejects your token | Use `demo-dashboard-token` for all accounts, or an account token from `ACCOUNT_DASHBOARD_TOKENS` |
| Want a clean slate | `docker compose down -v`, then `docker compose up --build` |

**Stop:** press `Ctrl+C`, then `docker compose down`. Add `-v` to also delete all database data.

---

## Project layout

```text
.
├── compose.yaml          # whole system: 2 services, 2 databases, RabbitMQ, frontend, generator
├── services/
│   ├── ingest/           # FastAPI app, Alembic migrations, tests
│   └── billing/          # FastAPI app, Alembic migrations, tests
├── frontend/             # React + TypeScript + Vite; src/lib holds pure helpers with tests
├── generator/            # replays events with duplicates, late and out-of-order delivery
├── scripts/              # seed, performance and load tools
├── database/init/        # database role setup
├── docs/                 # project documentation
├── shared-contracts/     # JSON schema for the usage event
├── DECISIONS.md
└── PERFORMANCE.md
```


Optional, for frontend development only (needs Node.js 22+): `cd frontend && npm install && npm run dev`.

---

## Author

**Ayushi Yadav** · [GitHub](https://github.com/AyuShi-yDv) · [LinkedIn](https://www.linkedin.com/in/ayushi-yadav-76b256266)
