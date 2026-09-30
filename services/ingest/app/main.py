import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from .auth import authenticate
from .config import settings
from .db import Session
from .outbox import backlog_size, run_publisher
from .ratelimit import FixedWindowLimiter
from .repository import store_event
from .schemas import UsageIn

limiter = FixedWindowLimiter(settings.rate_limit_per_minute)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Strict policy for every API response.
API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Looser policy only for the Swagger page: it needs its own scripts, styles and inline bootstrap script.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(run_publisher())
    yield
    task.cancel()


app = FastAPI(title="ingest-service", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    csp = DOCS_CSP if request.url.path == "/docs" else API_CSP
    response.headers["Content-Security-Policy"] = csp
    return response


@app.middleware("http")
async def body_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_body_bytes:
        return Response(status_code=413)
    return await call_next(request)


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        swagger_favicon_url="data:,",
    )


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