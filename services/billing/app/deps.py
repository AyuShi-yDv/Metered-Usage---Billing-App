"""Request-level authorization helpers shared by routers."""
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException

from .authorization import account_token_is_authorized, finance_token_is_authorized
from .config import settings


def require_finance(token: str) -> None:
    if not finance_token_is_authorized(token, settings.dashboard_token):
        raise HTTPException(401, "unauthorized")


def require_account(account_id: UUID, token: str) -> None:
    # Finance is explicitly cross-account; customer tokens are scoped to one account.
    if not account_token_is_authorized(account_id, token, settings.dashboard_token, settings.account_dashboard_tokens):
        raise HTTPException(403, "account access denied")


def require_utc_offsets(*values: datetime) -> None:
    if any(v.tzinfo is None or v.utcoffset() is None for v in values):
        raise HTTPException(422, "timestamps must include a timezone offset")
