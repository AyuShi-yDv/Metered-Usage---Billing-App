"""API-key authentication with a short per-process lookup cache."""
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .config import settings
from .db import Session
from .security import verify_secret

_cache: dict[str, tuple[float, dict | None]] = {}
_fetch_lock = asyncio.Lock()


@dataclass(frozen=True)
class AuthenticatedKey:
    account_id: UUID
    key_id: UUID


async def _lookup(prefix: str) -> dict | None:
    """Cached row for a key prefix (also caches misses so random prefixes cannot hammer the DB)."""
    ttl = settings.key_cache_ttl_seconds
    hit = _cache.get(prefix)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    async with _fetch_lock:  # single-flight refresh
        hit = _cache.get(prefix)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        async with Session() as db:
            row = (await db.execute(
                text("SELECT id, account_id, secret_hash, revoked_at, overlap_expires_at FROM api_keys WHERE prefix = :prefix"),
                {"prefix": prefix},
            )).mappings().first()
        value = dict(row) if row else None
        _cache[prefix] = (time.monotonic(), value)
        if len(_cache) > 10_000:
            now = time.monotonic()
            for key in [k for k, (ts, _) in _cache.items() if now - ts >= ttl]:
                del _cache[key]
        return value


def clear_cache() -> None:
    _cache.clear()


async def authenticate(api_key: str) -> AuthenticatedKey:
    row = await _lookup(api_key[:10])
    # Same error for unknown prefix and wrong secret: do not reveal which.
    if row is None or not verify_secret(api_key, row["secret_hash"]):
        raise HTTPException(401, "invalid API key")
    if row["revoked_at"] is not None:
        grace_end = row["overlap_expires_at"]  # rotation keeps the old key alive for a grace window
        if grace_end is None or grace_end < datetime.now(timezone.utc):
            raise HTTPException(401, "revoked API key")
    return AuthenticatedKey(account_id=row["account_id"], key_id=row["id"])
