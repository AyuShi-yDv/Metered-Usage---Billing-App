# Decisions

**Boundary.** Ingest owns API credentials, raw accepted events, and the outbox because these are write-path concerns. Billing owns plans, event facts, reports, rollups, and invoices; it never queries the ingest database.

**Billing unavailable.** Ingest still commits valid events and outbox rows. The dashboard is eventually consistent and should display its last update time; the publisher retries and failed messages are dead-lettered.

**Exactly once.** Delivery is at least once. `usage_events.event_id` prevents repeated HTTP ingestion and `billing_events.event_id` prevents repeated broker deliveries; outbox and event share one transaction.

**Late usage.** A month closes 48 hours after month end. Later events do not alter a finalized invoice: billing creates a next-invoice adjustment calculated from the corrected period delta. This is auditable but can surprise a customer later.

**With another week.** Add authenticated human users, credit notes, observability, and a production secrets manager. At 100x data, partition event facts by month and replace broad p95 scans with mergeable percentile sketches.
