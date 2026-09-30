"""API-key management for the dashboard: authorises the caller, then proxies to ingest's private listener."""
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response

from .. import ingest_client
from ..deps import require_account

router = APIRouter(prefix="/accounts/{account_id}/api-keys", tags=["api-keys"])


@router.get("")
async def list_keys(account_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    return await ingest_client.call("GET", "/v1/api-keys", params={"account_id": str(account_id)})


@router.post("", status_code=201)
async def create_key(account_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    return await ingest_client.call("POST", "/v1/api-keys", body={"account_id": str(account_id)})


@router.delete("/{key_id}", status_code=204)
async def revoke_key(account_id: UUID, key_id: UUID, x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    await ingest_client.call("DELETE", f"/v1/api-keys/{key_id}", params={"account_id": str(account_id)})
    return Response(status_code=204)


@router.post("/{key_id}/rotate", status_code=201)
async def rotate_key(account_id: UUID, key_id: UUID, overlap_seconds: int = Query(300, ge=0, le=86400), x_dashboard_token: str = Header(default="")):
    require_account(account_id, x_dashboard_token)
    return await ingest_client.call("POST", f"/v1/api-keys/{key_id}/rotate",
                                    params={"account_id": str(account_id), "overlap_seconds": overlap_seconds})
