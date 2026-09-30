import hmac
import json
from uuid import UUID


def _eq(a: str, b: str) -> bool:
    # Encode first: compare_digest raises TypeError on non-ASCII str, which would surface as a 500.
    return hmac.compare_digest(a.encode(), b.encode())


def account_token_is_authorized(account_id: UUID, token: str, finance_token: str, account_tokens_json: str) -> bool:
    """True for the explicit finance role or the token configured for exactly this account."""
    if _eq(token, finance_token):
        return True
    try:
        configured = json.loads(account_tokens_json)
        expected = configured.get(str(account_id)) if isinstance(configured, dict) else None
    except (TypeError, ValueError):
        expected = None
    return bool(expected) and _eq(token, expected)


def finance_token_is_authorized(token: str, finance_token: str) -> bool:
    return _eq(token, finance_token)
