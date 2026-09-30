# Metered Usage & Billing App

A full-stack microservices application for API usage metering, asynchronous billing, usage analytics, invoice generation, API key management, and plan comparison.

Built with **React + TypeScript + FastAPI + PostgreSQL + RabbitMQ + Docker**.

## ✨ Highlights

- API usage event ingestion with API-key authentication
- Idempotent usage processing using `event_id`
- Asynchronous ingest → RabbitMQ → billing pipeline
- Separate PostgreSQL databases for ingest and billing services
- Monthly plans, included usage allowance, base fees, and overage billing
- Hourly usage rollups with safe concurrent processing
- Invoice generation and invoice previews
- API key creation, rotation, listing, and revocation
- One-time display of newly generated API secrets
- Per-account rate limiting with `429` and `Retry-After`
- Hourly/daily usage dashboards
- Account search, pagination, and usage sorting
- p95 endpoint latency reporting
- Month-to-date usage and projected overage reporting
- Top-account overage reporting
- 30-day plan what-if comparison
- Live usage generation and dashboard refresh
- Automated backend tests
- SQL-based reporting and performance documentation
- Docker Compose setup for local development

---

## 🏗️ Architecture


                         ┌──────────────────────┐
                         │    React Frontend    │
                         │  TypeScript + Vite   │
                         │      :5173           │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Billing Service    │
                         │     FastAPI :8001    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Billing DB        │
                         │    PostgreSQL 16     │
                         └──────────────────────┘


┌──────────────────────┐
│      API Client      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    Ingest Service    │
│     FastAPI :8000    │
└──────────┬───────────┘
           │
           ├──────────────► Ingest DB
           │
           ▼
┌──────────────────────┐
│       RabbitMQ       │
│   Async Message Bus  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    Billing Service   │
│   Event Processing   │
└──────────────────────┘
```

The ingest and billing services are separate processes with separate PostgreSQL databases.

---

## 🛠️ Tech Stack

### Frontend

- React 18
- TypeScript
- Vite
- TanStack Query
- Responsive dashboard UI

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Async SQLAlchemy
- Pydantic v2
- Alembic

### Data & Messaging

- PostgreSQL 16
- RabbitMQ
- Transactional outbox pattern

### Infrastructure

- Docker
- Docker Compose

### Testing

- Pytest
- Integration tests
- Idempotency tests
- Concurrency tests
- SQL/reporting tests

---

## 📁 Project Structure

```text
.
├── compose.yml
├── README.md
├── PERFORMANCE.md
├── DECISIONS.md
│
├── database/
│   └── init/
│
├── services/
│   ├── ingest/
│   │   ├── app/
│   │   ├── alembic/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   └── billing/
│       ├── app/
│       ├── alembic/
│       ├── tests/
│       └── Dockerfile
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── Dockerfile
│
├── generator/
│   ├── main.py
│   └── Dockerfile
│
└── scripts/
    ├── seed.py
    ├── Dockerfile
    └── test.Dockerfile
```

---

# 🚀 Getting Started

## Prerequisites

Install:

- Docker Desktop
- Docker Compose
- Git
- Node.js 18+ (for local frontend development)

Check your installation:

```bash
docker --version
docker compose version
node --version
npm --version
```

## Clone the Repository

```bash
git clone https://github.com/AyuShi-yDv/Metered-Usage---Billing-App.git
cd Metered-Usage---Billing-App
```

## Start the Application

```bash
docker compose up --build
```

The application starts the required services, applies database migrations, and loads configured seed data.

For detached mode:

```bash
docker compose up --build -d
```

Check service status:

```bash
docker compose ps
```

---

# 🌐 Local URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Ingest API | http://localhost:8000 |
| Ingest Swagger | http://localhost:8000/docs |
| Billing API | http://localhost:8001 |
| Billing Swagger | http://localhost:8001/docs |
| RabbitMQ Management | http://localhost:15672 |

### RabbitMQ local credentials

The default Compose configuration uses:

```text
Username: app
Password: app
```

These values can be overridden through environment variables.

---

# 📊 Main Application Features

## Usage Dashboard

The dashboard provides:

- Usage time series
- Hourly/daily view
- Date range selection
- URL-persisted dashboard filters
- Billable usage information
- Projected overage
- Live refresh while the event generator is running

## Accounts

The accounts interface supports:

- Server-side pagination
- Search
- Usage sorting
- Account details

Account details include:

- Current plan
- Included allowance
- Allowance consumed
- Projected overage
- p95 endpoint latency

## API Key Management

Supported operations:

- Create API key
- List API keys
- Rotate API key
- Revoke API key

New API secrets are displayed only when generated and are not intended to be retrieved later.

## Invoices

The invoice interface supports:

- Invoice preview
- Billing-period selection
- Line-item breakdown
- Base fee
- Overage charges
- Adjustments
- Invoice totals
- Invoice finalization
- Print/save as PDF
- Previous invoice viewing

## Plan Comparison

The application provides plan comparison and what-if billing functionality based on recent usage.

---

# 🔑 Usage Ingestion

The ingest service exposes:

```http
POST /v1/usage
```

Usage events contain information such as:

```json
{
  "event_id": "evt_123456",
  "api_key": "api-key-value",
  "endpoint": "/v1/users",
  "timestamp": "2026-09-30T12:30:00Z",
  "duration_ms": 142,
  "status_code": 200
}
```

The ingestion path validates the request and hands billing work off asynchronously.

The ingestion request does not perform synchronous invoice rating.

---

# ♻️ Idempotency

Each usage event has a unique `event_id`.

Submitting the same event multiple times does not result in duplicate billing.

Idempotency is enforced at the database level and is covered by automated tests, including concurrent duplicate-processing scenarios.

---

# 💰 Billing Rules

The application uses the following billing rules:

```text
2xx → Billable
4xx → Billable
5xx → Not billable
```

## Money

Monetary values are represented using integer minor units rather than floating-point numbers.

Example:

```text
$12.34 → 1234 cents
```

Invoice-level calculations use half-up rounding.

## Plans

A plan contains:

- Monthly included allowance
- Monthly base fee
- Overage price per thousand calls

Each account has one plan.

---

# 📨 Asynchronous Processing

The event pipeline uses RabbitMQ:

```text
Client
  │
  ▼
Ingest API
  │
  ▼
Ingest Database / Outbox
  │
  ▼
RabbitMQ
  │
  ▼
Billing Consumer
  │
  ▼
Billing Database
  │
  ▼
Rollups / Invoices / Reports
```

This architecture keeps the ingestion path lightweight while allowing billing processing to happen asynchronously.

Retry and dead-letter behavior are included for message-processing failure scenarios.

---

# 🚦 Rate Limiting

The ingest service supports per-account rate limiting.

When the configured limit is exceeded, the API returns:

```http
429 Too Many Requests
```

with a:

```http
Retry-After
```

header.

The default local configuration is:

```env
RATE_LIMIT_PER_MINUTE=600
```

---

# 📈 Reporting

The reporting layer supports:

### Usage time series

- Hourly aggregation
- Daily aggregation
- Zero-filled missing intervals

### Endpoint performance

- p95 duration by endpoint
- PostgreSQL `percentile_cont`

### Billing status

- Month-to-date billable calls
- Monthly allowance
- Projected end-of-month overage

### Account ranking

- Top accounts by overage
- SQL ranking
- Month-over-month comparison

Reporting calculations are performed in SQL rather than through Python-side aggregation loops.

---

# 🧪 Testing

Run the ingest service tests:

```bash
docker compose --profile tests run --rm ingest-tests
```

Run the billing service tests:

```bash
docker compose --profile tests run --rm billing-tests
```

The tests cover areas including:

- Usage ingestion
- Idempotency
- Duplicate events
- Concurrent processing
- Billing calculations
- Money calculations
- Rollups
- SQL reporting

---

# 📦 Seed Data

The project includes a seed process for realistic development/testing data.

The default Compose configuration can load approximately:

```text
500,000 usage events
```

The seed operation is designed to be idempotent.

To disable event seeding:

```env
SEED_EVENTS=0
```

---

# ⚡ Performance

Performance testing is documented in:

```text
PERFORMANCE.md
```

The documentation covers:

- SQL queries being benchmarked
- `EXPLAIN ANALYZE`
- `EXPLAIN ANALYZE BUFFERS`
- Index selection
- Before/after performance
- Query planner behavior
- Row-estimate accuracy
- Large-volume testing

The reporting workload was evaluated using a large event dataset, including approximately 500,000 usage events.

---

# 🧠 Architecture Decisions

Important engineering decisions are documented in:

```text
DECISIONS.md
```

Topics include:

- Service boundaries
- Separate databases
- Asynchronous processing
- Outage behavior
- Idempotency/exactly-once critical operations
- Scaling considerations
- High-volume failure scenarios

---

# 🗃️ Database Migrations

Database schema changes are managed through Alembic.

The services apply migrations during startup.

The application does not rely on SQLAlchemy `create_all()` for schema creation.

---

# 🖥️ Frontend Development

To run the frontend separately:

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

Build the frontend:

```bash
npm run build
```

Run available project checks:

```bash
npm run check
```

---

# 🔄 Usage Generator

The project includes a background usage generator for testing live usage updates.

The event rate can be configured using:

```env
EVENTS_PER_SECOND=4
```

This allows the dashboard to be tested with continuously changing usage data.

---

# 🛑 Stop the Application

Stop the application:

```bash
docker compose down
```

To remove containers and local database volumes:

```bash
docker compose down -v
```

> Warning: `docker compose down -v` removes local PostgreSQL volumes and therefore deletes locally stored database data.

---

# 🔐 Environment & Security

Do not commit production secrets to GitHub.

Never commit:

- Production database passwords
- API secrets
- Authentication tokens
- RabbitMQ production credentials
- Cloud credentials
- Private keys

Use environment variables or a production secret manager instead.

A safe `.env.example` should contain placeholder values only.

---

# 📌 Local Ports

| Component | Port |
|---|---:|
| React Frontend | 5173 |
| Ingest API | 8000 |
| Billing API | 8001 |
| RabbitMQ AMQP | 5672 |
| RabbitMQ Management | 15672 |

PostgreSQL databases are exposed internally to the Docker network.

---

# 🚀 Production Deployment

The application is designed around independently deployable services.

A production deployment can use:

```text
                 Internet
                    │
                    ▼
              React Frontend
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
    Ingest Service       Billing Service
          │                   │
          ▼                   ▼
      RabbitMQ           PostgreSQL
```

For production deployment, use:

- Managed PostgreSQL
- Managed RabbitMQ
- HTTPS
- Secure environment variables
- Production authentication credentials
- Restricted database access
- Appropriate CORS configuration
- Monitoring and logging

The current Docker Compose configuration is primarily intended for local development and evaluation.

---

# 📚 Engineering Principles

This project follows several backend and distributed-systems principles:

- Integer-based monetary values
- UTC timestamps
- Database-enforced idempotency
- Separate service databases
- Asynchronous event processing
- Transactional outbox
- SQL-based reporting
- Alembic migrations
- API validation
- Safe concurrent processing
- Environment-based configuration
- Automated testing
- Containerized development

---

# 👩‍💻 Author

## Ayushi Yadav

GitHub:  
https://github.com/AyuShi-yDv

LinkedIn:  
https://www.linkedin.com/in/ayushi-yadav-76b256266

---

# 📄 Project

**Metered Usage & Billing App**

A full-stack engineering project demonstrating:

- Microservices
- REST APIs
- React development
- Async Python
- PostgreSQL
- SQL reporting
- RabbitMQ
- Billing systems
- Distributed processing
- Docker
- Automated testing
- Performance engineering

---

## ⭐ Repository

https://github.com/AyuShi-yDv/Metered-Usage---Billing-App
