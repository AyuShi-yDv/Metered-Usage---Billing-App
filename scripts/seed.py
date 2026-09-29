"""Bulk-load benchmark/demo data. Run after docker compose up with the DB URLs set."""
import asyncio, os, random, uuid, secrets, hashlib
from datetime import datetime, timedelta, timezone
import asyncpg

INGEST_DB=os.environ["INGEST_DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://")
BILLING_DB=os.environ["BILLING_DATABASE_URL"].replace("postgresql+asyncpg://","postgresql://")
EVENT_COUNT=int(os.getenv("SEED_EVENTS","500000"))
NOW=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
ENDPOINTS=("/v1/search","/v1/files","/v1/export","/v1/users")
STATUSES=(200,201,204,400,404,429,500,503)

async def batches(conn, table, columns, records, size=10000):
    batch=[]
    for record in records:
        batch.append(record)
        if len(batch)>=size:
            await conn.copy_records_to_table(table,records=batch,columns=columns); batch.clear()
    if batch: await conn.copy_records_to_table(table,records=batch,columns=columns)

async def main():
    ingest=await asyncpg.connect(INGEST_DB); billing=await asyncpg.connect(BILLING_DB)
    try:
        await billing.execute("CREATE TEMP TABLE seed_billing_events (LIKE billing_events INCLUDING DEFAULTS)")
        await ingest.execute("CREATE TEMP TABLE seed_ingest_events (LIKE usage_events INCLUDING DEFAULTS)")
        demo_account=uuid.UUID("00000000-0000-0000-0000-000000000001")
        accounts=[demo_account]+[uuid.uuid5(uuid.NAMESPACE_DNS,f"metered-demo-{i}") for i in range(1,50)]
        plans=[uuid.uuid5(uuid.NAMESPACE_DNS,f"metered-plan-{i}") for i in range(3)]
        await billing.executemany("INSERT INTO plans(id,name,included_calls,overage_cents_per_1000,monthly_base_fee_cents) VALUES($1,$2,$3,$4,$5) ON CONFLICT(id) DO NOTHING",[(plans[0],"Seed Starter",10000,250,1900),(plans[1],"Seed Growth",50000,180,7900),(plans[2],"Seed Scale",250000,120,29900)])
        await billing.executemany("INSERT INTO accounts(id,name) VALUES($1,$2) ON CONFLICT(id) DO NOTHING",[(a,f"Demo account {i+1:02d}") for i,a in enumerate(accounts)])
        await billing.executemany("INSERT INTO account_plans(id,account_id,plan_id,effective_from) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",[(uuid.uuid5(uuid.NAMESPACE_DNS,f"assignment-{a}"),a,plans[i%3],datetime(2020,1,1,tzinfo=timezone.utc)) for i,a in enumerate(accounts) if a != demo_account])
        api_key_ids=[uuid.uuid5(uuid.NAMESPACE_DNS,f"seed-key-{a}") for a in accounts]
        api_key_by_account=dict(zip(accounts,api_key_ids))
        def seed_hash():
            salt=secrets.token_bytes(16); secret=secrets.token_bytes(32)
            return salt.hex()+":"+hashlib.sha256(salt+secret).hexdigest()
        await ingest.executemany("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES($1,$2,$3,$4) ON CONFLICT(id) DO NOTHING",[(k,a,f"seed{i:04d}",seed_hash()) for i,(a,k) in enumerate(zip(accounts,api_key_ids))])
        event_rows=[]; duplicate_rows=[]
        for event_number in range(EVENT_COUNT):
            event_id=uuid.uuid4()
            idx=random.randrange(len(accounts)); age=timedelta(seconds=random.randrange(0,60*86400))
            happened=NOW-age+timedelta(minutes=random.randrange(0,60))
            row=(event_id,accounts[idx],random.choice(ENDPOINTS),happened,random.randint(1,5000),random.choice(STATUSES))
            event_rows.append(row)
            if event_number%100==0: duplicate_rows.append(row)
            if len(event_rows)>=10000:
                await batches(billing,"seed_billing_events",["event_id","account_id","endpoint","occurred_at","duration_ms","status_code"],event_rows)
                await batches(ingest,"seed_ingest_events",["event_id","account_id","api_key_id","endpoint","occurred_at","duration_ms","status_code"],[(r[0],r[1],api_key_by_account[r[1]],r[2],r[3],r[4],r[5]) for r in event_rows])
                event_rows.clear()
        if event_rows:
            await batches(billing,"seed_billing_events",["event_id","account_id","endpoint","occurred_at","duration_ms","status_code"],event_rows)
            await batches(ingest,"seed_ingest_events",["event_id","account_id","api_key_id","endpoint","occurred_at","duration_ms","status_code"],[(r[0],r[1],api_key_by_account[r[1]],r[2],r[3],r[4],r[5]) for r in event_rows])
        await batches(billing,"seed_billing_events",["event_id","account_id","endpoint","occurred_at","duration_ms","status_code"],duplicate_rows)
        await batches(ingest,"seed_ingest_events",["event_id","account_id","api_key_id","endpoint","occurred_at","duration_ms","status_code"],[(r[0],r[1],api_key_by_account[r[1]],r[2],r[3],r[4],r[5]) for r in duplicate_rows])
        await billing.execute("INSERT INTO billing_events(event_id,account_id,endpoint,occurred_at,duration_ms,status_code) SELECT event_id,account_id,endpoint,occurred_at,duration_ms,status_code FROM seed_billing_events ON CONFLICT(event_id) DO NOTHING")
        await ingest.execute("INSERT INTO usage_events(event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code) SELECT event_id,account_id,api_key_id,endpoint,occurred_at,duration_ms,status_code FROM seed_ingest_events ON CONFLICT(event_id) DO NOTHING")
        await billing.execute("""INSERT INTO hourly_usage_rollups(account_id,hour_start,endpoint,billable_calls,total_calls)
        SELECT account_id,date_trunc('hour',occurred_at),endpoint,count(*) FILTER(WHERE status_code BETWEEN 200 AND 499),count(*) FROM billing_events GROUP BY 1,2,3 ON CONFLICT(account_id,hour_start,endpoint) DO UPDATE SET billable_calls=excluded.billable_calls,total_calls=excluded.total_calls""")
        print(f"Copied {EVENT_COUNT+len(duplicate_rows):,} attempted deliveries; database event_id constraints retained {EVENT_COUNT:,} unique events across {len(accounts)} accounts and 3 plans. Seed facts span 60 days; the live generator separately emits events delayed by up to 23.8 hours.")
    finally:
        await ingest.close(); await billing.close()

if __name__=="__main__": asyncio.run(main())
