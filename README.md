# Metered API usage and billing

Two isolated FastAPI services use a transactional outbox and RabbitMQ to move usage from ingestion to billing. PostgreSQL is private to each service. The React dashboard reads only the billing API.

## Run

```sh
copy .env.example .env
docker compose up --build
```

Open `http://localhost:5173`. Startup migrations seed a Demo account and three plans; the generator creates a key through a private management listener and continuously sends events at `EVENTS_PER_SECOND`. Use `DASHBOARD_TOKEN` for the finance-wide dashboard, or the account-specific value in `ACCOUNT_DASHBOARD_TOKENS` for a customer-scoped view. Key management is proxied through billing; the ingest management port is internal to Compose, and a newly created/rotated secret is displayed once. The Postgres init script at `database/init/010-app-role.sql` creates separate non-superuser app roles; it runs only for empty data volumes.

## Safety and consistency

- API secrets are generated with `secrets`, returned once, and stored as salted SHA-256 digests. The high-entropy random keys allow a fast digest check for ingest latency.
- `event_id` is unique in both services. The message path is at-least-once; accounting is idempotent.
- Ingest commits the event and outbox record together. A publisher-confirmed message is safe to retry.
- Billing recomputes hour rollups under `FOR UPDATE SKIP LOCKED`; it never incrementally adds retryable counts. Transient consumer failures are retried with 1, 5, and 30 second broker delays before dead-lettering.
- Currency is integer cents. Overage uses integer half-up rounding once per invoice.
- Plan history is effective-dated with a PostgreSQL exclusion constraint. Mid-period invoices prorate each plan's allowance and base fee by its exact active duration; the what-if endpoint compares the previous 30 days with another plan.
- The compose stack includes a small live demo dataset. To load the required 500,000-event benchmark dataset, run `scripts/seed.py` against both service databases after startup (the volume seed is deliberately an explicit step so a clean boot remains quick).

## Tests

```sh
cd services/ingest && pytest
cd ../billing && pytest
```

Set `DATABASE_URL` to the migrated billing database and run `pytest -q` in `services/billing`; set it to the migrated ingest database for its idempotency test. Tests skip database integration cases when the variable is unset. To produce the 500k bulk dataset and benchmark evidence, export `INGEST_DATABASE_URL` and `BILLING_DATABASE_URL`, then run `python scripts/seed.py` and `python scripts/performance.py`.
