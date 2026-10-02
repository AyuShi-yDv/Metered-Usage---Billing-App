# Engineering Decisions

## 1. Service boundary

Ingest owns API authentication, usage-event validation, persistence,
and the transactional outbox. Billing owns billing events, plans,
rollups, invoices, and reporting. The services use separate databases
so the write-heavy ingestion path remains independent from billing work.

## 2. Billing service unavailable

If Billing is unavailable, Ingest does not wait for Billing to process
the event. The usage event and its outbox message are committed
transactionally first. The outbox publisher can continue delivery
through RabbitMQ, and Billing processes the event when it becomes
available again. From the caller's perspective, a valid usage request
can still receive HTTP 202.

## 3. Exactly-once effect under retries

Delivery is at-least-once, because messages can be retried or delivered
more than once. Database uniqueness on `usage_events.event_id` prevents
duplicate ingestion, while `billing_events.event_id` prevents duplicate
billing consumption, giving the system exactly-once counting/effect
rather than claiming exactly-once message delivery.

## 4. What I would change with another week

I would first improve the ingest latency path, because the latest
documented local benchmark is above the assignment's <50 ms p95 target.
I would also improve production observability and operational controls,
including authenticated human access, stronger production secret
management, and clearer monitoring of stale outbox/DLQ messages.

## 5. What breaks at 100x data volume

Broad p95 scans and very large event tables would become increasingly
expensive at much higher volumes. I would partition event data by time
and move large-scale percentile reporting toward mergeable percentile
sketches or another scalable analytical approach.
