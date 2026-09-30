import asyncio
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .bootstrap import seed_demo
from .config import settings
from .consumer import consumer_supervisor
from .db import Session
from .routers import accounts, invoices, keys, reports
from .worker import process_one_rollup

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


async def rollup_scheduler() -> None:
    """Drain pending (account, hour) rollup tasks; safe to run in several replicas."""
    while True:
        try:
            while await process_one_rollup():
                pass
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(random.uniform(1, 3))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await seed_demo()
    tasks = [asyncio.create_task(consumer_supervisor()), asyncio.create_task(rollup_scheduler())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="billing-service", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Dashboard-Token"],
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
    try:
        async with Session() as db:
            pending = (await db.execute(text("SELECT count(*) FROM rollup_tasks"))).scalar_one()
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"ok": True, "pending_rollups": pending}


for router in (reports.router, accounts.router, invoices.router, keys.router):
    app.include_router(router)