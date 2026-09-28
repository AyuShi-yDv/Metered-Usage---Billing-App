import asyncio, json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4
import aio_pika
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import text
from .config import settings
from .db import Session
from .reports import TIME_SERIES_SQL, P95_SQL, MTD_SQL, TOP_OVERAGE_SQL
from .worker import process_one_rollup
from .money import overage_cents

DEMO_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")

async def seed_demo() -> None:
    """Seed only business data; schemas always come from Alembic."""
    async with Session() as db, db.begin():
        await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'Demo account') ON CONFLICT DO NOTHING"), {"id": DEMO_ACCOUNT_ID})
        plan_id = UUID("00000000-0000-0000-0000-000000000010")
        await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:id,'Starter',10000,250,1900) ON CONFLICT DO NOTHING"), {"id": plan_id})
        await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(:id,:account,:plan,'2020-01-01T00:00:00Z') ON CONFLICT DO NOTHING"), {"id": UUID("00000000-0000-0000-0000-000000000011"),"account":DEMO_ACCOUNT_ID,"plan":plan_id})

async def consume() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel(); await channel.set_qos(prefetch_count=50)
    exchange = await channel.declare_exchange("usage", aio_pika.ExchangeType.FANOUT, durable=True)
    queue = await channel.declare_queue("billing.usage", durable=True, arguments={"x-dead-letter-exchange":"usage.dlx"})
    await queue.bind(exchange)
    async def handle(message: aio_pika.IncomingMessage):
        async with message.process(requeue=False):
            payload = json.loads(message.body)
            if payload.get("schema_version") != 1: raise ValueError("unsupported message schema")
            async with Session() as db, db.begin():
                event = UUID(payload["event_id"]); account = UUID(payload["account_id"]); occurred = datetime.fromisoformat(payload["timestamp"])
                result = await db.execute(text("""INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code)
                VALUES(:event,:account,:endpoint,:occurred,:duration,:status) ON CONFLICT(event_id) DO NOTHING"""), {"event":event,"account":account,"endpoint":payload["endpoint"],"occurred":occurred,"duration":payload["duration_ms"],"status":payload["status_code"]})
                if result.rowcount:
                    await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:account,date_trunc('hour',:occurred)) ON CONFLICT DO NOTHING"), {"account":account,"occurred":occurred})
    await queue.consume(handle)
    await asyncio.Future()

async def scheduler() -> None:
    while True:
        while await process_one_rollup(): pass
        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(_: FastAPI):
    await seed_demo()
    tasks = [asyncio.create_task(consume()), asyncio.create_task(scheduler())]
    yield
    for task in tasks: task.cancel()

app = FastAPI(title="billing-service", lifespan=lifespan)

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.get("/reports/usage/time-series")
async def time_series(account_id: UUID, start: datetime, end: datetime, granularity: str = Query("hour", pattern="^(hour|day)$")):
    if end <= start: raise HTTPException(422, "end must be after start")
    interval = "1 hour" if granularity == "hour" else "1 day"
    async with Session() as db:
        rows = (await db.execute(text(TIME_SERIES_SQL), {"account_id":account_id,"start":start,"end":end,"bucket":granularity,"interval":interval})).mappings().all()
    return {"data": rows}

@app.get("/reports/usage/p95")
async def p95(account_id: UUID, start: datetime, end: datetime):
    async with Session() as db: rows = (await db.execute(text(P95_SQL), {"account_id":account_id,"start":start,"end":end})).mappings().all()
    return {"data": rows}

@app.get("/reports/usage/mtd")
async def mtd(account_id: UUID):
    async with Session() as db: row = (await db.execute(text(MTD_SQL), {"account_id":account_id})).mappings().first()
    if not row: raise HTTPException(404, "account or active plan not found")
    projected = max(0, row["calls"] + row["projected_remaining_calls"] - row["included_calls"])
    return {**dict(row), "projected_overage_cents": overage_cents(projected, row["overage_cents_per_1000"])}

@app.get("/reports/usage/top-overage")
async def top_overage():
    async with Session() as db: rows = (await db.execute(text(TOP_OVERAGE_SQL))).mappings().all()
    return {"data": rows}

@app.post("/invoices/{account_id}/{period_start}")
async def create_invoice(account_id: UUID, period_start: datetime):
    period_start = period_start.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start.replace(year=period_start.year + 1, month=1) if period_start.month == 12 else period_start.replace(month=period_start.month + 1)
    async with Session() as db, db.begin():
        plan = (await db.execute(text("""SELECT p.* FROM account_plans ap JOIN plans p ON p.id=ap.plan_id WHERE ap.account_id=:account AND ap.effective_from<=:start AND (ap.effective_to IS NULL OR ap.effective_to>:start) FOR SHARE"""), {"account":account_id,"start":period_start})).mappings().first()
        if not plan: raise HTTPException(404, "no plan")
        calls = (await db.execute(text("SELECT COALESCE(sum(billable_calls),0)::bigint FROM hourly_usage_rollups WHERE account_id=:account AND hour_start>=:start AND hour_start<:end"), {"account":account_id,"start":period_start,"end":period_end})).scalar_one()
        overage = overage_cents(max(0,calls-plan["included_calls"]), plan["overage_cents_per_1000"]); invoice_id=uuid4()
        inserted = (await db.execute(text("""INSERT INTO invoices(id,account_id,period_start,period_end,status,base_fee_cents,overage_cents,total_cents) VALUES(:id,:account,:start,:end,'final',:base,:overage,:total) ON CONFLICT(account_id,period_start) DO NOTHING RETURNING id"""), {"id":invoice_id,"account":account_id,"start":period_start,"end":period_end,"base":plan["monthly_base_fee_cents"],"overage":overage,"total":plan["monthly_base_fee_cents"]+overage})).scalar_one_or_none()
        if not inserted:
            existing = (await db.execute(text("SELECT id,total_cents FROM invoices WHERE account_id=:account AND period_start=:start"), {"account":account_id,"start":period_start})).mappings().one()
            return {"invoice_id":str(existing["id"]),"total_cents":existing["total_cents"]}
        await db.execute(text("INSERT INTO invoice_lines(id,invoice_id,description,quantity,amount_cents) VALUES(:id,:invoice,'Monthly base fee',1,:base),(:id2,:invoice,'Overage calls',:quantity,:overage) ON CONFLICT DO NOTHING"), {"id":uuid4(),"id2":uuid4(),"invoice":invoice_id,"base":plan["monthly_base_fee_cents"],"quantity":max(0,calls-plan["included_calls"]),"overage":overage})
    return {"invoice_id":str(invoice_id),"total_cents":plan["monthly_base_fee_cents"]+overage}
