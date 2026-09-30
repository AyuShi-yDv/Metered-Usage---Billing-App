import asyncio, json, random, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4, UUID
import aio_pika
from fastapi import FastAPI, Header, HTTPException, Response, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .db import Session
from .schemas import UsageIn
from .security import verify_secret
from .config import settings

# ---------------------------------------------------------------------------
# Outbox publisher – runs as background task, drains with publisher confirms
# ---------------------------------------------------------------------------

async def publish_outbox() -> None:
    backoff = 1.0
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            backoff = 1.0
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                exchange = await channel.declare_exchange("usage", aio_pika.ExchangeType.FANOUT, durable=True)
                while True:
                    async with Session() as db:
                        rows = (await db.execute(text(
                            "SELECT id, payload FROM outbox_messages WHERE published_at IS NULL ORDER BY created_at LIMIT 100"
                        ))).mappings().all()
                    published_ids = []
                    for row in rows:
                        try:
                            await exchange.publish(
                                aio_pika.Message(
                                    json.dumps(row["payload"], default=str).encode(),
                                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                    message_id=str(row["id"]),
                                ), ""
                            )
                        except Exception:
                            if published_ids:
                                async with Session() as db, db.begin():
                                    await db.execute(
                                        text("UPDATE outbox_messages SET published_at=now(), attempts=attempts+1 WHERE id=ANY(CAST(:ids AS uuid[])) AND published_at IS NULL"),
                                        {"ids": published_ids},
                                    )
                            raise
                        published_ids.append(row["id"])
                    if published_ids:
                        async with Session() as db, db.begin():
                            await db.execute(
                                text("UPDATE outbox_messages SET published_at=now(), attempts=attempts+1 WHERE id=ANY(CAST(:ids AS uuid[])) AND published_at IS NULL"),
                                {"ids": published_ids},
                            )
                    await asyncio.sleep(.25)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(backoff * random.uniform(.75, 1.25))
            backoff = min(backoff * 2, 30.0)

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(publish_outbox())
    yield
    task.cancel()

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="ingest-service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    return response

@app.middleware("http")
async def body_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > settings.max_body_bytes:
        return Response(status_code=413)
    body = await request.body()
    if len(body) > settings.max_body_bytes:
        return Response(status_code=413)
    return await call_next(request)

# ---------------------------------------------------------------------------
# In-process key cache and rate limiter (avoids DB round-trips on hot path)
# ---------------------------------------------------------------------------

_key_cache: dict[str, tuple[float, dict]] = {}
_key_lock = asyncio.Lock()

_rate_limits: dict[UUID, tuple[float, int]] = {}
_rate_lock = asyncio.Lock()

async def _lookup_key(prefix: str) -> dict:
    """Return cached API-key row, fetching from DB at most once per 60 s per prefix."""
    now = time.monotonic()
    cached = _key_cache.get(prefix)
    if cached and now - cached[0] < 60.0:
        return cached[1]
    # Double-checked lock: only one coroutine does the DB fetch
    async with _key_lock:
        cached = _key_cache.get(prefix)
        if cached and time.monotonic() - cached[0] < 60.0:
            return cached[1]
        async with Session() as db:
            row = (await db.execute(text("""
                SELECT id, account_id, secret_hash, revoked_at, overlap_expires_at
                FROM api_keys WHERE prefix = :prefix
            """), {"prefix": prefix})).mappings().first()
        if not row:
            raise HTTPException(401, "invalid API key")
        key_info = dict(row)
        _key_cache[prefix] = (time.monotonic(), key_info)
        return key_info

async def _check_rate_limit(account_id: UUID, limit: int = 600, window: float = 60.0) -> tuple[bool, int]:
    """Sliding-window in-memory rate limiter; no DB writes on the hot path."""
    now = time.monotonic()
    async with _rate_lock:
        win_start, count = _rate_limits.get(account_id, (now, 0))
        if now - win_start >= window:
            win_start, count = now, 0
        if count >= limit:
            return False, max(1, int(window - (now - win_start)) + 1)
        _rate_limits[account_id] = (win_start, count + 1)
        return True, 0

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.post("/v1/usage", status_code=202)
async def ingest(body: UsageIn, x_api_key: str = Header(min_length=20, max_length=256)):
    key_info = await _lookup_key(x_api_key[:10])

    if not verify_secret(x_api_key, key_info["secret_hash"]):
        raise HTTPException(401, "invalid API key")

    now_utc = datetime.now(timezone.utc)
    if key_info["revoked_at"] and (not key_info["overlap_expires_at"] or key_info["overlap_expires_at"] < now_utc):
        raise HTTPException(401, "revoked API key")

    account_id: UUID = key_info["account_id"]
    api_key_id: UUID = key_info["id"]

    allowed, retry_after = await _check_rate_limit(account_id)
    if not allowed:
        return Response(content="rate limit exceeded", status_code=429, headers={"Retry-After": str(retry_after)})

    payload = {
        "schema_version": 1,
        "event_id": str(body.event_id),
        "account_id": str(account_id),
        "endpoint": body.endpoint,
        "timestamp": body.timestamp.isoformat(),
        "duration_ms": body.duration_ms,
        "status_code": body.status_code,
    }

    async with Session() as db, db.begin():
        await db.execute(text("""WITH inserted AS (
          INSERT INTO usage_events(event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code)
          VALUES(:event,:account,:key,:endpoint,:occurred,:duration,:status)
          ON CONFLICT(event_id) DO NOTHING RETURNING event_id
        )
        INSERT INTO outbox_messages(id,topic,payload)
        SELECT :outbox_id,'usage.accepted',CAST(:payload AS jsonb)
        WHERE EXISTS (SELECT 1 FROM inserted)"""), {
            "event": body.event_id,
            "account": account_id,
            "key": api_key_id,
            "endpoint": body.endpoint,
            "occurred": body.timestamp,
            "duration": body.duration_ms,
            "status": body.status_code,
            "outbox_id": uuid4(),
            "payload": json.dumps(payload),
        })

    return Response(status_code=status.HTTP_202_ACCEPTED)
