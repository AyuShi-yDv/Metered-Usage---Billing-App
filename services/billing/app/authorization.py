import hmac
import json
from uuid import UUID


def account_token_is_authorized(account_id: UUID, token: str, finance_token: str, account_tokens_json: str) -> bool:
    """Return true for the explicit finance role or the matching account token."""
    if hmac.compare_digest(token, finance_token):
        return True
    try:
        configured = json.loads(account_tokens_json)
        expected = configured.get(str(account_id)) if isinstance(configured, dict) else None
    except (TypeError, ValueError):
        expected = None
    return bool(expected) and hmac.compare_digest(token, expected)
