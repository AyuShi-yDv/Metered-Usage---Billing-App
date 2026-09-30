"""HTTP client for ingest's private key-management listener, with a small circuit breaker.

Create/rotate are never retried (a timeout could otherwise mint a second secret); GETs retry with backoff.
"""
import asyncio
import random
import time

import httpx
from fastapi import HTTPException

from .config import settings

_failures = 0
_open_until = 0.0


async def call(method: str, path: str, *, params=None, body=None):
    global _failures, _open_until
    if time.monotonic() < _open_until:
        raise HTTPException(503, "key management service temporarily unavailable")
    attempts = 3 if method == "GET" else 1
    response = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
                response = await client.request(method, f"{settings.ingest_management_url}{path}", params=params, json=body,
                                                headers={"X-Internal-Token": settings.internal_token})
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("upstream failure", request=response.request, response=response)
            _failures, _open_until = 0, 0.0
            break
        except httpx.HTTPError:
            _failures += 1
            if _failures >= 5:
                _open_until = time.monotonic() + 15
            if attempt + 1 == attempts:
                raise HTTPException(503, "key management service unavailable")
            await asyncio.sleep(0.1 * (2 ** attempt) * random.uniform(0.75, 1.25))
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "key management request failed")
    return None if response.status_code == 204 else response.json()
