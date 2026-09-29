# Decisions

**Boundary.** Ingest owns API credentials, raw accepted events, and the outbox because these are write-path concerns. Billing owns plans, event facts, reports, rollups, and invoices; it never queries the ingest database.

**Billing unavailable.** Ingest still commits valid events and outbox rows, so the dashboard may show stale numbers while events queue. The UI has no staleness watermark or dead-letter alert/replay workflow yet; publishers retry and exhausted messages are retained in the DLQ for an operator.

**Exactly once.** Delivery is at least once. `usage_events.event_id` prevents repeated HTTP ingestion and `billing_events.event_id` prevents repeated broker deliveries; outbox and event share one transaction.

**Late usage.** A month closes 48 hours after month end. Later events do not alter a finalized invoice: billing creates a next-invoice adjustment calculated from the corrected period delta. This is auditable but can surprise a customer later.

**Plan changes and what-if.** Plan ranges cannot overlap, and a future change closes the current range and starts another in one transaction. Invoice base fees, included calls, and overage are prorated by exact active seconds, with cents rounded after segment amounts are summed; the what-if view applies an alternative plan to the same trailing 30 days.

**Key management.** Public ingestion is on port 8000; key mutation lives on a separate 8002 listener that is not published by Compose. Demo finance has an explicit cross-account token, while optional per-account credentials cannot authorize another account; production should replace static token configuration with an authenticated identity provider. The billing proxy forwards its service token, retries GETs only, and does not replay create/rotate because a timeout could otherwise create another secret.

**With another week.** Add authenticated human users, credit notes, observability, and a production secrets manager. At 100x data, partition event facts by month and replace broad p95 scans with mergeable percentile sketches.
