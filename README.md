# Metered API usage and billing

Two isolated FastAPI services use a transactional outbox and RabbitMQ to move usage from ingestion to billing. PostgreSQL is private to each service. The React dashboard reads only the billing API.

## Run

```sh
copy .env.example .env
docker compose up --build
```

Open `http://localhost:5173`. The seed on service startup creates a Demo account and API key. The generator uses that key only when `DEMO_API_KEY` is supplied; otherwise seed usage through `POST /v1/usage` after creating a key.

## Safety and consistency

- API secrets are generated with `secrets`, returned once, and stored as a PBKDF2 hash.
- `event_id` is unique in both services. The message path is at-least-once; accounting is idempotent.
- Ingest commits the event and outbox record together. A publisher-confirmed message is safe to retry.
- Billing recomputes hour rollups under `FOR UPDATE SKIP LOCKED`; it never incrementally adds retryable counts.
- Currency is integer cents. Overage uses integer half-up rounding once per invoice.

## Tests

```sh
cd services/ingest && pytest
cd ../billing && pytest
```

The integration/concurrency test suite needs a PostgreSQL `DATABASE_URL`; unit tests do not.
