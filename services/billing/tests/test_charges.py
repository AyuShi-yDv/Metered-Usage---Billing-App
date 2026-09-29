from app.charges import PERIOD_CHARGES_SQL, WHAT_IF_SQL


def test_invoice_proration_prices_plan_segments_before_rounding():
    sql = PERIOD_CHARGES_SQL.text.lower()
    assert "effective_from < period.period_end" in sql
    assert "effective_to" in sql
    assert "segment_seconds / period_seconds" in sql
    assert "round(base_amount + overage_amount)" in sql
    assert "round(base_amount + overage_amount) - round(base_amount)" in sql
    assert "status_code between 200 and 499" in sql


def test_what_if_is_one_parameterized_last_30_day_query():
    sql = WHAT_IF_SQL.text.lower()
    assert "interval '30 days'" in sql
    assert ":account" in sql and ":plan_id" in sql
    assert "count(*) filter" in sql
