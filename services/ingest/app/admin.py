"""Private API-key management listener; this port is internal to Compose only."""
import hmac
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Response
from sqlalchemy import text

from .config import settings
from .db import Session
from .schemas import KeyCreate, KeyCreated
from .security import hash_secret, new_secret

app = FastAPI(title="ingest-private-key-management")


def check_internal(token: str) -> None:
    if not hmac.compare_digest(token.encode(), settings.internal_token.encode()):
        raise HTTPException(401, "unauthorized")


@app.post("/v1/api-keys", response_model=KeyCreated, status_code=201)
async def create_key(body: KeyCreate, x_internal_token: str = Header(default="")):
    check_internal(x_internal_token)
    prefix, secret = new_secret()
    key_id = uuid4()
    async with Session() as db, db.begin():
        await db.execute(text("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES(:id,:account,:prefix,:hash)"),
                         {"id": key_id, "account": body.account_id, "prefix": prefix, "hash": hash_secret(secret)})
    return KeyCreated(id=key_id, prefix=prefix, secret=secret)


@app.get("/v1/api-keys")
async def list_keys(account_id: UUID, x_internal_token: str = Header(default="")):
    check_internal(x_internal_token)
    async with Session() as db:
        rows = (await db.execute(text("SELECT id,prefix,created_at,revoked_at FROM api_keys WHERE account_id=:account ORDER BY created_at DESC"),
                                 {"account": account_id})).mappings().all()
    return {"data": rows}


@app.delete("/v1/api-keys/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, account_id: UUID, x_internal_token: str = Header(default="")):
    check_internal(x_internal_token)
    async with Session() as db, db.begin():
        result = await db.execute(text("UPDATE api_keys SET revoked_at=now(),overlap_expires_at=NULL WHERE id=:id AND account_id=:account AND revoked_at IS NULL"),
                                  {"id": key_id, "account": account_id})
        if not result.rowcount:
            raise HTTPException(404, "key not found")
    return Response(status_code=204)


@app.post("/v1/api-keys/{key_id}/rotate", response_model=KeyCreated, status_code=201)
async def rotate_key(key_id: UUID, account_id: UUID, overlap_seconds: int = Query(300, ge=0, le=86400), x_internal_token: str = Header(default="")):
    check_internal(x_internal_token)
    prefix, secret = new_secret()
    new_id = uuid4()
    async with Session() as db, db.begin():
        result = await db.execute(text("UPDATE api_keys SET revoked_at=now(),overlap_expires_at=now()+make_interval(secs=>:seconds) WHERE id=:id AND account_id=:account AND revoked_at IS NULL"),
                                  {"seconds": overlap_seconds, "id": key_id, "account": account_id})
        if not result.rowcount:
            raise HTTPException(404, "active key not found")
        await db.execute(text("INSERT INTO api_keys(id,account_id,prefix,secret_hash) VALUES(:id,:account,:prefix,:hash)"),
                         {"id": new_id, "account": account_id, "prefix": prefix, "hash": hash_secret(secret)})
    return KeyCreated(id=new_id, prefix=prefix, secret=secret)
