import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import authenticate
from .config import settings
from .db import Session
from .outbox import backlog_size, run_publisher
from .ratelimit import FixedWindowLimiter
from .repository import store_event
from .schemas import UsageIn

limiter = FixedWindowLimiter(settings.rate_limit_per_minute)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(run_publisher())
    yield
    task.cancel()


app = FastAPI(title="ingest-service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
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
    if length and length.isdigit() and int(length) > settings.max_body_bytes:
        return Response(status_code=413)
    return await call_next(request)


@app.get("/healthz")
async def healthz():
    """Liveness + DB reachability. `outbox_backlog` > 0 for long means billing/broker trouble."""
    try:
        backlog = await backlog_size()
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "outbox_backlog": backlog}


@app.post("/v1/usage", status_code=status.HTTP_202_ACCEPTED)
async def ingest(body: UsageIn, x_api_key: str = Header(min_length=20, max_length=256)):
    """Validate, authenticate, persist event + outbox row in one transaction, return. No rating here."""
    key = await authenticate(x_api_key)
    allowed, retry_after = limiter.check(key.account_id)
    if not allowed:
        return Response("rate limit exceeded", status_code=429, headers={"Retry-After": str(retry_after)})
    async with Session() as db, db.begin():
        await store_event(db, account_id=key.account_id, api_key_id=key.key_id, event=body)
    return Response(status_code=status.HTTP_202_ACCEPTED)
