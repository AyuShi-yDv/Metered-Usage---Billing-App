"""Persistence for accepted usage events (the only place that writes usage_events/outbox)."""
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import UsageIn

# One statement: the outbox row exists if and only if the event row was newly
# inserted. A duplicate event_id hits ON CONFLICT DO NOTHING, inserts nothing,
# and therefore publishes nothing.
STORE_EVENT_SQL = text("""
WITH inserted AS (
  INSERT INTO usage_events(event_id, account_id, api_key_id, endpoint, occurred_at, duration_ms, status_code)
  VALUES (:event, :account, :key, :endpoint, :occurred, :duration, :status)
  ON CONFLICT (event_id) DO NOTHING
  RETURNING event_id
)
INSERT INTO outbox_messages(id, topic, payload)
SELECT :outbox_id, 'usage.accepted', CAST(:payload AS jsonb)
WHERE EXISTS (SELECT 1 FROM inserted)
""")


def build_payload(account_id: UUID, event: UsageIn) -> dict:
    return {
        "schema_version": 1,
        "event_id": str(event.event_id),
        "account_id": str(account_id),
        "endpoint": event.endpoint,
        "timestamp": event.timestamp.isoformat(),
        "duration_ms": event.duration_ms,
        "status_code": event.status_code,
    }


async def store_event(db: AsyncSession, *, account_id: UUID, api_key_id: UUID, event: UsageIn) -> bool:
    """Insert event + outbox row atomically. Returns False when event_id was already stored."""
    result = await db.execute(STORE_EVENT_SQL, {
        "event": event.event_id, "account": account_id, "key": api_key_id,
        "endpoint": event.endpoint, "occurred": event.timestamp,
        "duration": event.duration_ms, "status": event.status_code,
        "outbox_id": uuid4(), "payload": json.dumps(build_payload(account_id, event)),
    })
    return result.rowcount == 1
