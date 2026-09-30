# Final validation notes

## Implemented in this snapshot

- Invoice preview UI with billing-period selection, line items, totals, print/save-to-PDF action, finalization, and finalized-invoice history.
- API-key management UI with create, one-time secret display, list, rotation with a five-minute overlap, and revoke.
- Plan comparison UI backed by the existing 30-day what-if endpoint, plus scheduled future plan changes.
- Account-detail API now exposes the active `plan_id`, so the plan comparison UI identifies the current plan without guessing by name.
- Ingest benchmark rewritten to warm the request path, use modest concurrency, report p50/p95/max, and fail unless all requests return 202 and p95 < 50 ms.

## Validation performed in the available build environment

- Python `compileall` over services, generator and scripts: PASS.
- Frontend dependency installation/build could not be completed in this environment because npm dependency installation timed out and the environment has no Docker/Compose.
- Docker/Compose execution of the full stack could not be performed because the Docker executable is not installed in this environment.
- The backend pytest collection could not run as a full suite here because the host environment is missing the repository's runtime dependency setup (for example `asyncpg`), and service-local imports require the service working directory/PYTHONPATH.

## Required final machine-side verification

From the repository root on a machine with Docker:

```sh
docker compose up --build
```

Then, in a second terminal:

```sh
docker compose --profile tests run --rm ingest-tests
docker compose --profile tests run --rm billing-tests
docker compose --profile tools run --rm ops-tools ingest_load.py
```

The last command must print `PASS: ingest p95 < 50 ms` and a p95 below 50 ms. This result is deliberately not fabricated in this archive because the build environment used for preparation did not contain Docker.
