# Message contract: ingest -> billing

| Item | Value |
|---|---|
| Exchange | `usage` (fanout, durable) |
| Queue | `billing.usage` (durable, `x-dead-letter-exchange=usage.dlx`) — **declared by both services with identical arguments** |
| Dead-letter | exchange `usage.dlx` -> queue `billing.usage.dead` |
| Retry | TTL queues `billing.retry.1s/5s/30s` dead-letter back into `usage`; 3 attempts then DLQ |
| Payload | `usage-event.schema.json` (`schema_version` 1) |
| Delivery | at-least-once; billing de-duplicates on `event_id` (primary key) |

Why the queue is declared on the producer side too: a fanout exchange with no bound queue silently drops
messages, so events published before billing first starts would be lost. If you change the queue arguments,
change them in `services/ingest/app/outbox.py` **and** `services/billing/app/consumer.py`, or RabbitMQ will
refuse the second declaration.
