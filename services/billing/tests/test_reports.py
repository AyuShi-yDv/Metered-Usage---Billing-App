from app.reports import MTD_SQL, P95_SQL, TIME_SERIES_SQL, TOP_OVERAGE_SQL


def test_report_sql_uses_required_primitives():
    assert "generate_series" in TIME_SERIES_SQL and "LEFT JOIN" in TIME_SERIES_SQL
    assert "percentile_cont" in P95_SQL
    assert "DENSE_RANK" in TOP_OVERAGE_SQL
    assert "projected_overage_cents" in MTD_SQL and "CEIL(" in MTD_SQL


def test_money_is_rounded_exactly_once_in_sql():
    # Regression: "(x + 500) / 1000" on numeric followed by a ::bigint cast rounds twice (+1 cent).
    for sql in (MTD_SQL, TOP_OVERAGE_SQL):
        assert "+ 500" not in sql and "+500" not in sql
        assert "round(" in sql
