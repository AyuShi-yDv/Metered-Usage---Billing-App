"""Broker consumer: usage.accepted -> billing_events (+ a rollup task), idempotently."""
import asyncio
import json
import random
from datetime import datetime
from uuid import UUID

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import Session

EXCHANGE, DEAD_EXCHANGE, RETRY_EXCHANGE = "usage", "usage.dlx", "usage.retry"
QUEUE, DEAD_QUEUE = "billing.usage", "billing.usage.dead"  # QUEUE args must match services/ingest/app/outbox.py
RETRY_LADDER = (("retry.1s", 1000), ("retry.5s", 5000), ("retry.30s", 30000))
REQUIRED = {"event_id", "account_id", "endpoint", "timestamp", "duration_ms", "status_code"}


class InvalidMessage(ValueError):
    """Permanently bad payload: retrying cannot help, send straight to the dead-letter queue."""


def parse_message(body: bytes) -> dict:
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not REQUIRED.issubset(payload):
            raise InvalidMessage("unknown schema or missing fields")
        parsed = {
            "event": UUID(payload["event_id"]),
            "account": UUID(payload["account_id"]),
            "endpoint": str(payload["endpoint"])[:256],
            "occurred": datetime.fromisoformat(payload["timestamp"]),
            "duration": payload["duration_ms"],
            "status": payload["status_code"],
        }
    except InvalidMessage:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidMessage(str(exc)) from exc
    if parsed["occurred"].tzinfo is None:
        raise InvalidMessage("timestamp needs an offset")
    if not (isinstance(parsed["duration"], int) and 0 <= parsed["duration"] <= 3_600_000):
        raise InvalidMessage("duration_ms out of range")
    if not (isinstance(parsed["status"], int) and 100 <= parsed["status"] <= 599):
        raise InvalidMessage("status_code out of range")
    return parsed


async def apply_usage_event(db: AsyncSession, parsed: dict) -> bool:
    """Persist one event. Returns False for a duplicate event_id (the DB primary key decides, not Python).

    The rollup task is only created for newly inserted events, so a redelivery does no extra work.
    """
    created = await db.execute(
        text("INSERT INTO accounts(id,name) VALUES(:account,:name) ON CONFLICT(id) DO NOTHING"),
        {"account": parsed["account"], "name": f"Account {str(parsed['account'])[:8]}"})
    if created.rowcount:  # first sighting of this account: put it on the Starter plan
        await db.execute(text(
            "INSERT INTO account_plans(id,account_id,plan_id,effective_from) "
            "SELECT gen_random_uuid(), :account, id, '2020-01-01T00:00:00Z' FROM plans WHERE name='Starter' ON CONFLICT DO NOTHING"),
            {"account": parsed["account"]})
    inserted = await db.execute(text(
        "INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) "
        "VALUES(:event,:account,:endpoint,:occurred,:duration,:status) ON CONFLICT(event_id) DO NOTHING"), parsed)
    if not inserted.rowcount:
        return False
    await db.execute(
        text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:account,date_trunc('hour',CAST(:occurred AS timestamptz))) ON CONFLICT DO NOTHING"),
        {"account": parsed["account"], "occurred": parsed["occurred"]})
    return True


async def consume() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel(publisher_confirms=True)
    await channel.set_qos(prefetch_count=50)
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)
    dead_exchange = await channel.declare_exchange(DEAD_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True)
    await (await channel.declare_queue(DEAD_QUEUE, durable=True)).bind(dead_exchange)
    retry_exchange = await channel.declare_exchange(RETRY_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
    for route, delay in RETRY_LADDER:  # TTL queues that dead-letter back into the main exchange
        retry_queue = await channel.declare_queue(f"billing.{route}", durable=True,
                                                 arguments={"x-message-ttl": delay, "x-dead-letter-exchange": EXCHANGE})
        await retry_queue.bind(retry_exchange, routing_key=route)
    queue = await channel.declare_queue(QUEUE, durable=True, arguments={"x-dead-letter-exchange": DEAD_EXCHANGE})
    await queue.bind(exchange)

    def dead(message: aio_pika.IncomingMessage, reason: str, retries: int = 0):
        return dead_exchange.publish(aio_pika.Message(
            message.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers={"failure": reason, "x-retries": retries}), routing_key="")

    async def handle(message: aio_pika.IncomingMessage) -> None:
        try:
            parsed = parse_message(message.body)
        except InvalidMessage:
            await dead(message, "invalid_message")
            await message.ack()
            return
        try:
            async with Session() as db, db.begin():
                await apply_usage_event(db, parsed)
            await message.ack()
        except asyncio.CancelledError:
            raise
        except Exception:  # transient (DB down, deadlock): bounded retry ladder, then DLQ
            retries = int((message.headers or {}).get("x-retries", 0))
            if retries >= len(RETRY_LADDER):
                await dead(message, "retries_exhausted", retries)
            else:
                headers = dict(message.headers or {}); headers["x-retries"] = retries + 1
                await retry_exchange.publish(aio_pika.Message(
                    message.body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT, headers=headers,
                    message_id=message.message_id), routing_key=RETRY_LADDER[retries][0])
            await message.ack()

    await queue.consume(handle)
    await asyncio.Future()  # run until cancelled


async def consumer_supervisor() -> None:
    backoff = 1.0
    while True:
        try:
            await consume()
            backoff = 1.0
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(backoff * random.uniform(0.75, 1.25))
            backoff = min(backoff * 2, 30.0)
