import asyncio, json, random
import httpx
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import aio_pika
from fastapi import FastAPI, HTTPException, Query, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .config import settings
from .db import Session
from .reports import TIME_SERIES_SQL, P95_SQL, MTD_SQL, TOP_OVERAGE_SQL
from .worker import process_one_rollup
from .charges import PERIOD_CHARGES_SQL, WHAT_IF_SQL
from .authorization import account_token_is_authorized

DEMO_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")

async def seed_demo() -> None:
    """Seed only business data; schemas always come from Alembic."""
    async with Session() as db, db.begin():
        await db.execute(text("INSERT INTO accounts(id,name) VALUES(:id,'Demo account') ON CONFLICT DO NOTHING"), {"id": DEMO_ACCOUNT_ID})
        plan_id = UUID("00000000-0000-0000-0000-000000000010")
        await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:id,'Starter',10000,250,1900) ON CONFLICT DO NOTHING"), {"id": plan_id})
        await db.execute(text("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES(:id,'Growth',50000,180,7900),(:id2,'Scale',250000,120,29900) ON CONFLICT DO NOTHING"), {"id": UUID("00000000-0000-0000-0000-000000000012"), "id2": UUID("00000000-0000-0000-0000-000000000013")})
        await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(:id,:account,:plan,'2020-01-01T00:00:00Z') ON CONFLICT DO NOTHING"), {"id": UUID("00000000-0000-0000-0000-000000000011"),"account":DEMO_ACCOUNT_ID,"plan":plan_id})

async def consume() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel(publisher_confirms=True); await channel.set_qos(prefetch_count=50)
    exchange = await channel.declare_exchange("usage", aio_pika.ExchangeType.FANOUT, durable=True)
    dead_exchange = await channel.declare_exchange("usage.dlx", aio_pika.ExchangeType.FANOUT, durable=True)
    dead_queue = await channel.declare_queue("billing.usage.dead", durable=True)
    await dead_queue.bind(dead_exchange)
    retry_exchange = await channel.declare_exchange("usage.retry", aio_pika.ExchangeType.DIRECT, durable=True)
    for route, delay in (("retry.1s",1000),("retry.5s",5000),("retry.30s",30000)):
        retry_queue = await channel.declare_queue(f"billing.{route}",durable=True,arguments={"x-message-ttl":delay,"x-dead-letter-exchange":"usage"})
        await retry_queue.bind(retry_exchange,routing_key=route)
    queue = await channel.declare_queue("billing.usage", durable=True, arguments={"x-dead-letter-exchange":"usage.dlx"})
    await queue.bind(exchange)
    async def handle(message: aio_pika.IncomingMessage):
        try:
            payload = json.loads(message.body)
            required={"event_id","account_id","endpoint","timestamp","duration_ms","status_code"}
            if payload.get("schema_version") != 1 or not required.issubset(payload):
                raise ValueError("invalid usage message")
        except Exception:
            await dead_exchange.publish(aio_pika.Message(message.body,delivery_mode=aio_pika.DeliveryMode.PERSISTENT,headers={"failure":"invalid_message"}),"")
            await message.ack()
            return
        try:
            async with Session() as db, db.begin():
                event = UUID(payload["event_id"]); account = UUID(payload["account_id"]); occurred = datetime.fromisoformat(payload["timestamp"])
                await db.execute(text("INSERT INTO accounts(id,name) VALUES(:account,:name) ON CONFLICT(id) DO NOTHING"), {"account":account,"name":f"Account {str(account)[:8]}"})
                starter = (await db.execute(text("SELECT id FROM plans WHERE name='Starter'"))).scalar_one_or_none()
                if starter:
                    await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(gen_random_uuid(),:account,:plan,'2020-01-01T00:00:00Z') ON CONFLICT DO NOTHING"), {"account":account,"plan":starter})
                result = await db.execute(text("""INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code)
                VALUES(:event,:account,:endpoint,:occurred,:duration,:status) ON CONFLICT(event_id) DO NOTHING"""), {"event":event,"account":account,"endpoint":payload["endpoint"],"occurred":occurred,"duration":payload["duration_ms"],"status":payload["status_code"]})
                if result.rowcount:
                    await db.execute(text("INSERT INTO rollup_tasks(account_id,hour_start) VALUES(:account,date_trunc('hour',:occurred)) ON CONFLICT DO NOTHING"), {"account":account,"occurred":occurred})
            await message.ack()
        except asyncio.CancelledError:
            raise
        except Exception:
            retries=int((message.headers or {}).get("x-retries",0))
            if retries >= 3:
                await dead_exchange.publish(aio_pika.Message(message.body,delivery_mode=aio_pika.DeliveryMode.PERSISTENT,headers={"failure":"retries_exhausted","x-retries":retries}),"")
            else:
                route=("retry.1s","retry.5s","retry.30s")[retries]
                headers=dict(message.headers or {}); headers["x-retries"]=retries+1
                await retry_exchange.publish(aio_pika.Message(message.body,delivery_mode=aio_pika.DeliveryMode.PERSISTENT,headers=headers,message_id=message.message_id),routing_key=route)
            await message.ack()
    await queue.consume(handle)
    await asyncio.Future()

async def scheduler() -> None:
    while True:
        try:
            while await process_one_rollup(): pass
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(random.uniform(1,3))

async def consumer_supervisor() -> None:
    backoff=1.0
    while True:
        try:
            await consume()
            backoff=1.0
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(backoff*random.uniform(.75,1.25))
            backoff=min(backoff*2,30.0)

@asynccontextmanager
async def lifespan(_: FastAPI):
    await seed_demo()
    tasks = [asyncio.create_task(consumer_supervisor()), asyncio.create_task(scheduler())]
    yield
    for task in tasks: task.cancel()

app = FastAPI(title="billing-service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type","X-Dashboard-Token"],
)

@app.middleware("http")
async def security_headers(request, call_next):
    response=await call_next(request)
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("Referrer-Policy","no-referrer")
    response.headers.setdefault("X-Frame-Options","DENY")
    response.headers.setdefault("Content-Security-Policy","default-src 'none'; frame-ancestors 'none'")
    return response

def authorize(account_id: UUID, token: str) -> None:
    # Finance is explicitly cross-account. Customer tokens are configured per
    # account, so possessing one account's credential cannot authorize another.
    if not account_token_is_authorized(account_id, token, settings.dashboard_token, settings.account_dashboard_tokens):
        raise HTTPException(403,"account access denied")

def require_utc_offsets(*values: datetime) -> None:
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise HTTPException(422,"timestamps must include a timezone offset")

@app.get("/healthz")
async def healthz(): return {"ok": True}

@app.get("/plans")
async def plans(x_dashboard_token: str = Header(default="")):
    if not __import__("hmac").compare_digest(x_dashboard_token, settings.dashboard_token):
        raise HTTPException(401, "unauthorized")
    async with Session() as db:
        rows = (await db.execute(text("SELECT id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents FROM plans ORDER BY monthly_base_fee_cents,id"))).mappings().all()
    return {"data": rows}

@app.get("/accounts/{account_id}/plans")
async def account_plans(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    async with Session() as db:
        rows = (await db.execute(text("SELECT id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents FROM plans ORDER BY monthly_base_fee_cents,id"))).mappings().all()
    return {"data": rows}

@app.post("/accounts/{account_id}/plan-changes", status_code=201)
async def schedule_plan_change(account_id: UUID, plan_id: UUID, effective_at: datetime | None = None, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    effective_at = effective_at or datetime.now(timezone.utc)
    require_utc_offsets(effective_at)
    effective_at = effective_at.astimezone(timezone.utc)
    if effective_at < datetime.now(timezone.utc):
        raise HTTPException(422, "plan changes cannot be backdated")
    async with Session() as db, db.begin():
        account = (await db.execute(text("SELECT id FROM accounts WHERE id=:account FOR UPDATE"), {"account": account_id})).scalar_one_or_none()
        if not account:
            raise HTTPException(404, "account not found")
        plan = (await db.execute(text("SELECT id FROM plans WHERE id=:plan"), {"plan": plan_id})).scalar_one_or_none()
        if not plan:
            raise HTTPException(404, "plan not found")
        pending = (await db.execute(text("SELECT id FROM account_plans WHERE account_id=:account AND effective_from>now() LIMIT 1 FOR UPDATE"), {"account": account_id})).first()
        if pending:
            raise HTTPException(409, "an account can have only one pending plan change")
        current = (await db.execute(text("SELECT id,effective_from FROM account_plans WHERE account_id=:account AND effective_from<=now() AND (effective_to IS NULL OR effective_to>now()) FOR UPDATE"), {"account": account_id})).mappings().first()
        if not current or effective_at <= current["effective_from"]:
            raise HTTPException(409, "effective time must follow the active plan start")
        await db.execute(text("UPDATE account_plans SET effective_to=:effective WHERE id=:id"), {"effective": effective_at, "id": current["id"]})
        assignment_id = uuid4()
        await db.execute(text("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES(:id,:account,:plan,:effective)"), {"id": assignment_id, "account": account_id, "plan": plan_id, "effective": effective_at})
    return {"id": str(assignment_id), "account_id": str(account_id), "plan_id": str(plan_id), "effective_at": effective_at}

@app.get("/accounts/{account_id}/what-if")
async def what_if(account_id: UUID, plan_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    async with Session() as db:
        row = (await db.execute(WHAT_IF_SQL, {"account": account_id, "plan_id": plan_id})).mappings().first()
    if not row:
        raise HTTPException(404, "account, active plan, or comparison plan not found")
    return dict(row)

async def call_ingest_management(method: str, path: str, account_id: UUID, *, params=None, body=None):
    global _management_failures, _management_open_until
    if time.monotonic() < _management_open_until:
        raise HTTPException(503, "key management service temporarily unavailable")
    attempts = 3 if method == "GET" else 1  # never replay non-idempotent create/rotate operations
    try:
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
                    response = await client.request(method, f"{settings.ingest_management_url}{path}", params=params,
                        json=body, headers={"X-Internal-Token": settings.internal_token})
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("upstream failure", request=response.request, response=response)
                _management_failures = 0
                _management_open_until = 0.0
                break
            except httpx.HTTPError:
                _management_failures += 1
                if _management_failures >= 5:
                    _management_open_until = time.monotonic() + 15
                if attempt + 1 == attempts:
                    raise
                await asyncio.sleep((0.1 * (2 ** attempt)) * random.uniform(0.75, 1.25))
    except httpx.HTTPError:
        raise HTTPException(503, "key management service unavailable")
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "key management request failed")
    return Response(status_code=204) if response.status_code == 204 else response.json()

_management_failures = 0
_management_open_until = 0.0

@app.get("/accounts/{account_id}/api-keys")
async def account_keys(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    return await call_ingest_management("GET", "/v1/api-keys", account_id, params={"account_id": str(account_id)})

@app.post("/accounts/{account_id}/api-keys", status_code=201)
async def account_create_key(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    return await call_ingest_management("POST", "/v1/api-keys", account_id, body={"account_id": str(account_id)})

@app.delete("/accounts/{account_id}/api-keys/{key_id}", status_code=204)
async def account_revoke_key(account_id: UUID, key_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    return await call_ingest_management("DELETE", f"/v1/api-keys/{key_id}", account_id, params={"account_id": str(account_id)})

@app.post("/accounts/{account_id}/api-keys/{key_id}/rotate", status_code=201)
async def account_rotate_key(account_id: UUID, key_id: UUID, overlap_seconds: int = Query(300, ge=0, le=86400), x_dashboard_token: str = Header(default="")):
    authorize(account_id, x_dashboard_token)
    return await call_ingest_management("POST", f"/v1/api-keys/{key_id}/rotate", account_id,
        params={"account_id": str(account_id), "overlap_seconds": overlap_seconds})

@app.get("/reports/usage/time-series")
async def time_series(account_id: UUID, start: datetime, end: datetime, granularity: str = Query("hour", pattern="^(hour|day)$"), x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    require_utc_offsets(start,end)
    if end <= start: raise HTTPException(422, "end must be after start")
    interval = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    async with Session() as db:
        rows = (await db.execute(text(TIME_SERIES_SQL), {"account_id":account_id,"start":start,"end":end,"bucket":granularity,"interval":interval})).mappings().all()
    return {"data": rows}

@app.get("/reports/usage")
async def usage_report(report: str = Query(..., pattern="^(time_series|p95|mtd|top_overage)$"), account_id: UUID | None = None, start: datetime | None = None, end: datetime | None = None, granularity: str = Query("hour",pattern="^(hour|day)$"), x_dashboard_token: str = Header(default="")):
    if report == "top_overage":
        if not __import__("hmac").compare_digest(x_dashboard_token,settings.dashboard_token): raise HTTPException(401,"unauthorized")
        async with Session() as db: rows=(await db.execute(text(TOP_OVERAGE_SQL))).mappings().all()
        return {"data":rows}
    if not account_id: raise HTTPException(422,"account_id is required")
    authorize(account_id,x_dashboard_token)
    if report == "mtd":
        async with Session() as db: row=(await db.execute(text(MTD_SQL),{"account_id":account_id})).mappings().first()
        if not row: raise HTTPException(404,"active plan missing")
        return dict(row)
    if not start or not end: raise HTTPException(422,"a valid start and end are required")
    require_utc_offsets(start,end)
    if end<=start: raise HTTPException(422,"end must be after start")
    if report == "p95":
        sql, params = P95_SQL,{"account_id":account_id,"start":start,"end":end}
    else:
        sql, params = TIME_SERIES_SQL,{"account_id":account_id,"start":start,"end":end,"bucket":granularity,"interval":timedelta(hours=1) if granularity=="hour" else timedelta(days=1)}
    async with Session() as db: rows=(await db.execute(text(sql),params)).mappings().all()
    return {"data":rows}

@app.get("/reports/usage/p95")
async def p95(account_id: UUID, start: datetime, end: datetime, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    require_utc_offsets(start,end)
    if end<=start: raise HTTPException(422,"end must be after start")
    async with Session() as db: rows = (await db.execute(text(P95_SQL), {"account_id":account_id,"start":start,"end":end})).mappings().all()
    return {"data": rows}

@app.get("/reports/usage/mtd")
async def mtd(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    async with Session() as db: row = (await db.execute(text(MTD_SQL), {"account_id":account_id})).mappings().first()
    if not row: raise HTTPException(404, "account or active plan not found")
    return dict(row)

@app.get("/reports/usage/top-overage")
async def top_overage(x_dashboard_token: str = Header(default="")):
    if not __import__("hmac").compare_digest(x_dashboard_token, settings.dashboard_token): raise HTTPException(401,"unauthorized")
    async with Session() as db: rows = (await db.execute(text(TOP_OVERAGE_SQL))).mappings().all()
    return {"data": rows}

@app.post("/invoices/{account_id}/{period_start}")
async def create_invoice(account_id: UUID, period_start: datetime, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    require_utc_offsets(period_start)
    period_start = period_start.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start.replace(year=period_start.year + 1, month=1) if period_start.month == 12 else period_start.replace(month=period_start.month + 1)
    if period_end > datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=48):
        raise HTTPException(409,"invoice period is not closed; it closes 48 hours after month end")
    async with Session() as db, db.begin():
        lock_scope=f"{account_id}:{period_start.isoformat()}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),{"scope":lock_scope})
        charges = (await db.execute(PERIOD_CHARGES_SQL, {"account": account_id, "start": period_start, "end": period_end})).mappings().first()
        if not charges or charges["base_fee_cents"] is None: raise HTTPException(404, "no plan")
        calls = charges["calls"]; base_fee = charges["base_fee_cents"]; overage = charges["overage_cents"]; invoice_id=uuid4()
        invoice_total = charges["total_cents"]
        inserted = (await db.execute(text("""INSERT INTO invoices(id,account_id,period_start,period_end,status,base_fee_cents,overage_cents,total_cents) VALUES(:id,:account,:start,:end,'final',:base,:overage,:total) ON CONFLICT(account_id,period_start) DO NOTHING RETURNING id"""), {"id":invoice_id,"account":account_id,"start":period_start,"end":period_end,"base":base_fee,"overage":overage,"total":invoice_total})).scalar_one_or_none()
        if not inserted:
            existing = (await db.execute(text("SELECT id,total_cents FROM invoices WHERE account_id=:account AND period_start=:start"), {"account":account_id,"start":period_start})).mappings().one()
            return {"invoice_id":str(existing["id"]),"total_cents":existing["total_cents"]}
        await db.execute(text("INSERT INTO invoice_lines(id,invoice_id,description,quantity,amount_cents) VALUES(:id,:invoice,'Prorated monthly base fee',1,:base),(:id2,:invoice,'Prorated overage',1,:overage) ON CONFLICT DO NOTHING"), {"id":uuid4(),"id2":uuid4(),"invoice":invoice_id,"base":base_fee,"overage":overage})
        adjustment_total = 0
        adjustments = (await db.execute(text("SELECT id,amount_cents,source_period_start FROM late_adjustments WHERE account_id=:account AND applied_invoice_id IS NULL FOR UPDATE"),{"account":account_id})).mappings().all()
        if adjustments:
            adjustment_total=sum(row["amount_cents"] for row in adjustments)
            for row in adjustments:
                await db.execute(text("INSERT INTO invoice_lines(id,invoice_id,description,quantity,amount_cents,source_period_start) VALUES(:id,:invoice,'Late usage adjustment',1,:amount,:source)"),{"id":uuid4(),"invoice":invoice_id,"amount":row["amount_cents"],"source":row["source_period_start"]})
                await db.execute(text("UPDATE late_adjustments SET applied_invoice_id=:invoice WHERE id=:id"),{"invoice":invoice_id,"id":row["id"]})
            await db.execute(text("UPDATE invoices SET total_cents=total_cents+:amount WHERE id=:invoice"),{"amount":adjustment_total,"invoice":invoice_id})
    return {"invoice_id":str(invoice_id),"total_cents":invoice_total+adjustment_total}

@app.get("/accounts")
async def list_accounts(page: int = Query(1,ge=1), page_size: int = Query(20,ge=1,le=100), search: str = "", sort: str = Query("usage",pattern="^(usage|name)$"), x_dashboard_token: str = Header(default="")):
    if not __import__("hmac").compare_digest(x_dashboard_token, settings.dashboard_token): raise HTTPException(401,"unauthorized")
    order = "calls DESC" if sort == "usage" else "name ASC"
    sql = text(f"""WITH usage AS (SELECT account_id,sum(billable_calls)::bigint calls FROM hourly_usage_rollups WHERE hour_start>=date_trunc('month',now()) GROUP BY account_id)
    SELECT a.id,a.name,COALESCE(u.calls,0)::bigint calls,count(*) OVER() total FROM accounts a LEFT JOIN usage u ON u.account_id=a.id
    WHERE a.name ILIKE :search ORDER BY {order},a.id LIMIT :limit OFFSET :offset""")
    async with Session() as db:
        rows=(await db.execute(sql,{"search":f"%{search[:100]}%","limit":page_size,"offset":(page-1)*page_size})).mappings().all()
    return {"data":rows,"page":page,"page_size":page_size,"total":rows[0]["total"] if rows else 0}

@app.get("/accounts/{account_id}")
async def account_detail(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    sql=text("""WITH plan AS (SELECT p.name,p.included_calls,p.overage_cents_per_1000,p.monthly_base_fee_cents FROM account_plans ap JOIN plans p ON p.id=ap.plan_id WHERE ap.account_id=:account AND ap.effective_from<=now() AND (ap.effective_to IS NULL OR ap.effective_to>now()) ORDER BY ap.effective_from DESC LIMIT 1),
    usage AS (SELECT COALESCE(sum(billable_calls),0)::bigint calls FROM hourly_usage_rollups WHERE account_id=:account AND hour_start>=date_trunc('month',now())),
    latency AS (SELECT jsonb_agg(jsonb_build_object('endpoint',endpoint,'p95_duration_ms',p95)) endpoints FROM (SELECT endpoint,percentile_cont(.95) WITHIN GROUP(ORDER BY duration_ms) p95 FROM billing_events WHERE account_id=:account AND occurred_at>=date_trunc('month',now()) GROUP BY endpoint) x)
    SELECT a.id,a.name AS account_name,plan.name AS plan_name,plan.included_calls,plan.overage_cents_per_1000,plan.monthly_base_fee_cents,usage.calls,
    ((GREATEST(usage.calls + ((usage.calls::numeric/GREATEST(EXTRACT(EPOCH FROM now()-date_trunc('month',now())),1))*EXTRACT(EPOCH FROM (date_trunc('month',now())+interval '1 month'-now()))) - plan.included_calls,0)*plan.overage_cents_per_1000+500)/1000)::bigint projected_overage_cents,
    COALESCE(latency.endpoints,'[]'::jsonb) endpoints FROM accounts a CROSS JOIN plan CROSS JOIN usage CROSS JOIN latency WHERE a.id=:account""")
    async with Session() as db: row=(await db.execute(sql,{"account":account_id})).mappings().first()
    if not row: raise HTTPException(404,"account not found")
    return dict(row)

@app.get("/invoices/{account_id}")
async def invoices(account_id: UUID, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    async with Session() as db: rows=(await db.execute(text("SELECT i.*,jsonb_agg(to_jsonb(l)-'invoice_id') FILTER(WHERE l.id IS NOT NULL) lines FROM invoices i LEFT JOIN invoice_lines l ON l.invoice_id=i.id WHERE i.account_id=:account GROUP BY i.id ORDER BY i.period_start DESC"),{"account":account_id})).mappings().all()
    return {"data":rows}

@app.get("/invoices/preview/{account_id}/{period_start}")
async def invoice_preview(account_id: UUID, period_start: datetime, x_dashboard_token: str = Header(default="")):
    authorize(account_id,x_dashboard_token)
    require_utc_offsets(period_start)
    start=period_start.astimezone(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
    async with Session() as db: row=(await db.execute(PERIOD_CHARGES_SQL,{"account":account_id,"start":start,"end":end})).mappings().first()
    if not row or row["base_fee_cents"] is None: raise HTTPException(404,"account plan missing")
    result = dict(row)
    names = ", ".join(dict.fromkeys(segment["plan_name"] for segment in (result["plan_segments"] or [])))
    return {"period_start":start,"period_end":end,**result,"plan_name":names,"monthly_base_fee_cents":result["base_fee_cents"],"total_cents":result["total_cents"],"finalizable":end<=datetime.now(timezone.utc)-__import__("datetime").timedelta(hours=48)}
