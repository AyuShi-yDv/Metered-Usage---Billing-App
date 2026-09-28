"""Load generator: duplicates ~10%, late/out-of-order events ~15%."""
import asyncio, os, random
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import httpx

INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8000")
RATE = float(os.getenv("EVENTS_PER_SECOND", "4"))
TOKEN = os.getenv("INTERNAL_TOKEN", "change-me-in-production")
ACCOUNT = UUID("00000000-0000-0000-0000-000000000001")

async def get_key(client: httpx.AsyncClient) -> str:
    response = await client.post(f"{INGEST_URL}/v1/api-keys", json={"account_id":str(ACCOUNT)}, headers={"X-Internal-Token":TOKEN})
    response.raise_for_status(); return response.json()["secret"]

async def main():
    async with httpx.AsyncClient(timeout=2) as client:
        while True:
            try: key = await get_key(client); break
            except httpx.HTTPError: await asyncio.sleep(2)
        previous = None
        while True:
            now = datetime.now(timezone.utc)
            event_id = previous if previous and random.random() < .10 else uuid4()
            previous = event_id
            late = timedelta(hours=random.uniform(0, 23.8)) if random.random() < .15 else timedelta()
            payload = {"event_id":str(event_id),"endpoint":random.choice(["/v1/search","/v1/files","/v1/export"]),"timestamp":(now-late).isoformat(),"duration_ms":random.randint(5,1200),"status_code":random.choices([200,201,400,404,500],[65,5,12,8,10])[0]}
            try: await client.post(f"{INGEST_URL}/v1/usage", json=payload, headers={"X-API-Key":key})
            except httpx.HTTPError: pass
            await asyncio.sleep(1 / RATE)
asyncio.run(main())
