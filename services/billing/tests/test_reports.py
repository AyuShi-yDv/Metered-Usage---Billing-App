from app.reports import TIME_SERIES_SQL, P95_SQL, MTD_SQL, TOP_OVERAGE_SQL
def test_report_sql_uses_required_primitives():
    assert "generate_series" in TIME_SERIES_SQL and "LEFT JOIN" in TIME_SERIES_SQL
    assert "percentile_cont" in P95_SQL
    assert "DENSE_RANK" in TOP_OVERAGE_SQL
    assert "projected_overage_cents" in MTD_SQL
    assert "CEIL(" in MTD_SQL
