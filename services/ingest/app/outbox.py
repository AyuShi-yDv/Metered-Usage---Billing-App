"""Transactional-outbox publisher.

Rows are claimed with FOR UPDATE SKIP LOCKED, so any number of publisher
loops (one per uvicorn worker, or several replicas) never publish the same row
twice concurrently. Delivery to the broker is still at-least-once: a crash
between publish and commit re-sends, and billing de-duplicates on event_id.

The queue is declared here as well as in billing (identical arguments). With a
bare fanout exchange and no bound queue, RabbitMQ drops messages, which would
lose events published before billing first starts; declaring the durable queue
on the producer side closes that window.
"""
from __future__ import annotations

import asyncio
import json
import random
import time

import aio_pika
from sqlalchemy import text

from .config import settings
from .db import Session

EXCHANGE = "usage"
DEAD_EXCHANGE = "usage.dlx"
QUEUE = "billing.usage"  # must match services/billing/app/consumer.py
QUEUE_ARGUMENTS = {"x-dead-letter-exchange": DEAD_EXCHANGE}

CLAIM_SQL = text("""
SELECT id, payload FROM outbox_messages
WHERE published_at IS NULL
ORDER BY created_at
LIMIT :limit
FOR UPDATE SKIP LOCKED
""")
MARK_PUBLISHED_SQL = text(
    "UPDATE outbox_messages SET published_at = now(), attempts = attempts + 1 WHERE id = ANY(CAST(:ids AS uuid[]))"
)
MARK_FAILED_SQL = text("UPDATE outbox_messages SET attempts = attempts + 1, last_error = :error WHERE id = :id")
CLEANUP_SQL = text("""
DELETE FROM outbox_messages WHERE id IN (
  SELECT id FROM outbox_messages
  WHERE published_at IS NOT NULL AND published_at < now() - make_interval(hours => :hours)
  LIMIT 5000
)""")
BACKLOG_SQL = text("SELECT count(*) FROM (SELECT 1 FROM outbox_messages WHERE published_at IS NULL LIMIT 10001) s")


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractExchange:
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)
    await channel.declare_exchange(DEAD_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)
    queue = await channel.declare_queue(QUEUE, durable=True, arguments=QUEUE_ARGUMENTS)
    await queue.bind(exchange)
    return exchange


async def drain_once(exchange: aio_pika.abc.AbstractExchange, batch_size: int) -> int:
    """Claim, publish (with broker confirms) and mark one batch. Returns rows claimed."""
    failure: Exception | None = None
    async with Session() as db, db.begin():
        rows = (await db.execute(CLAIM_SQL, {"limit": batch_size})).mappings().all()
        published: list = []
        for row in rows:
            try:
                await exchange.publish(
                    aio_pika.Message(
                        json.dumps(row["payload"], default=str).encode(),
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        message_id=str(row["id"]),
                    ),
                    routing_key="",
                )
                published.append(row["id"])
            except Exception as exc:  # broker down / nack: keep what succeeded, retry the rest later
                failure = exc
                await db.execute(MARK_FAILED_SQL, {"id": row["id"], "error": repr(exc)[:500]})
                break
        if published:
            await db.execute(MARK_PUBLISHED_SQL, {"ids": published})
    if failure:
        raise failure
    return len(rows)


async def backlog_size() -> int:
    async with Session() as db:
        return int((await db.execute(BACKLOG_SQL)).scalar_one())


async def _cleanup() -> None:
    async with Session() as db, db.begin():
        await db.execute(CLEANUP_SQL, {"hours": settings.outbox_retention_hours})


async def run_publisher() -> None:
    """Background loop. Ingest keeps accepting traffic whatever happens here."""
    backoff = 1.0
    last_cleanup = 0.0
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                exchange = await declare_topology(channel)
                backoff = 1.0
                while True:
                    claimed = await drain_once(exchange, settings.outbox_batch_size)
                    if time.monotonic() - last_cleanup > 3600:
                        await _cleanup()
                        last_cleanup = time.monotonic()
                    if claimed < settings.outbox_batch_size:
                        await asyncio.sleep(settings.outbox_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(backoff * random.uniform(0.75, 1.25))
            backoff = min(backoff * 2, 30.0)
