from uuid import UUID

import pytest
from app.authorization import account_token_is_authorized


def test_account_dashboard_token_is_scoped_to_its_account():
    account_one = UUID("00000000-0000-0000-0000-000000000001")
    account_two = UUID("00000000-0000-0000-0000-000000000002")
    configured = '{"00000000-0000-0000-0000-000000000001":"account-one-token"}'
    assert account_token_is_authorized(account_one, "account-one-token", "finance", configured)
    assert not account_token_is_authorized(account_two, "account-one-token", "finance", configured)


def test_finance_dashboard_token_has_explicit_cross_account_role():
    account_two = UUID("00000000-0000-0000-0000-000000000002")
    assert account_token_is_authorized(account_two, "finance", "finance", "{}")
