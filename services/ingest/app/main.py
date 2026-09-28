import asyncio, json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
import aio_pika
from fastapi import FastAPI, Header, HTTPException, Response, status, Request
from sqlalchemy import text
from .db import Session
from .schemas import UsageIn, KeyCreate, KeyCreated
from .security import hash_secret, new_secret, verify_secret
from .config import settings

async def publish_outbox() -> None:
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                exchange = await channel.declare_exchange("usage", aio_pika.ExchangeType.FANOUT, durable=True)
                while True:
                    async with Session() as db, db.begin():
                        rows = (await db.execute(text("SELECT id, payload FROM outbox_messages WHERE published_at IS NULL ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 100"))).mappings().all()
                        for row in rows:
                            await exchange.publish(aio_pika.Message(json.dumps(row["payload"], default=str).encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT, message_id=str(row["id"])), "")
                            await db.execute(text("UPDATE outbox_messages SET published_at=now(), attempts=attempts+1 WHERE id=:id"), {"id": row["id"]})
                    await asyncio.sleep(.25)
        except Exception:
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(publish_outbox())
    yield
    task.cancel()

app = FastAPI(title="ingest-service", lifespan=lifespan)

@app.middleware("http")
async def body_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > settings.max_body_bytes:
        return Response(status_code=413)
    body = await request.body()
    if len(body) > settings.max_body_bytes:
        return Response(status_code=413)
    return await call_next(request)

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.post("/v1/api-keys", response_model=KeyCreated, status_code=201)
async def create_key(body: KeyCreate, x_internal_token: str = Header(default="")):
    if not __import__("hmac").compare_digest(x_internal_token, settings.internal_token): raise HTTPException(401, "unauthorized")
    prefix, secret = new_secret(); key_id = uuid4()
    async with Session() as db, db.begin():
        await db.execute(text("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES(:id,:account,:prefix,:hash)"), {"id": key_id, "account": body.account_id, "prefix": prefix, "hash": hash_secret(secret)})
    return KeyCreated(id=key_id, prefix=prefix, secret=secret)

@app.post("/v1/usage", status_code=202)
async def ingest(body: UsageIn, x_api_key: str = Header(min_length=20, max_length=256)):
    prefix = x_api_key[:10]
    async with Session() as db, db.begin():
        key = (await db.execute(text("SELECT id,account_id,secret_hash,revoked_at,overlap_expires_at FROM api_keys WHERE prefix=:prefix"), {"prefix": prefix})).mappings().first()
        if not key or not verify_secret(x_api_key, key["secret_hash"]): raise HTTPException(401, "invalid API key")
        if key["revoked_at"] and (not key["overlap_expires_at"] or key["overlap_expires_at"] < datetime.now(timezone.utc)): raise HTTPException(401, "revoked API key")
        result = await db.execute(text("""INSERT INTO usage_events(event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code)
          VALUES(:event,:account,:key,:endpoint,:occurred,:duration,:status) ON CONFLICT(event_id) DO NOTHING"""), {"event": body.event_id, "account": key["account_id"], "key": key["id"], "endpoint": body.endpoint, "occurred": body.timestamp, "duration": body.duration_ms, "status": body.status_code})
        if result.rowcount:
            payload = {"schema_version": 1, "event_id": str(body.event_id), "account_id": str(key["account_id"]), "endpoint": body.endpoint, "timestamp": body.timestamp.isoformat(), "duration_ms": body.duration_ms, "status_code": body.status_code}
            await db.execute(text("INSERT INTO outbox_messages(id,topic,payload) VALUES(:id,'usage.accepted',CAST(:payload AS jsonb))"), {"id": uuid4(), "payload": json.dumps(payload)})
    return Response(status_code=status.HTTP_202_ACCEPTED)
