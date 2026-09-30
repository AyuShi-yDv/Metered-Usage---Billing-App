from datetime import datetime, timedelta, timezone

from app.invoices import GRACE, build_lines, is_closed, month_bounds

UTC = timezone.utc


def test_month_bounds_handle_december_and_february():
    assert month_bounds(datetime(2024, 12, 31, 23, tzinfo=UTC)) == (datetime(2024, 12, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC))
    assert month_bounds(datetime(2024, 2, 10, tzinfo=UTC))[1] == datetime(2024, 3, 1, tzinfo=UTC)


def test_month_bounds_normalise_offsets_to_utc():
    start, _ = month_bounds(datetime.fromisoformat("2024-03-01T00:30:00+02:00"))  # still Feb 29 in UTC
    assert start == datetime(2024, 2, 1, tzinfo=UTC)


def test_period_closes_48_hours_after_month_end():
    end = datetime(2024, 2, 1, tzinfo=UTC)
    assert not is_closed(end, end + GRACE - timedelta(seconds=1))
    assert is_closed(end, end + GRACE)


def test_line_items_sum_to_total():
    charges = {"calls": 1500, "overage_calls": 500, "base_fee_cents": 1000, "overage_cents": 250, "total_cents": 1250,
               "plan_segments": [{"plan_name": "Starter"}, {"plan_name": "Starter"}]}
    lines = build_lines(charges)
    assert sum(line["amount_cents"] for line in lines) == charges["total_cents"]
    assert all(isinstance(line["amount_cents"], int) for line in lines)
    assert "Starter" in lines[1]["description"] and lines[2]["quantity"] == 500
