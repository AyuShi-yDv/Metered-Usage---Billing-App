from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import UsageIn


def event(timestamp):
    return {"event_id": str(uuid4()), "endpoint": "/v1/test", "timestamp": timestamp.isoformat(), "duration_ms": 10, "status_code": 200}


def test_usage_accepts_utc_and_offsets():
    parsed = UsageIn.model_validate(event(datetime.now(timezone.utc)))
    assert parsed.timestamp.tzinfo is not None


def test_usage_accepts_small_clock_skew_and_24h_late():
    UsageIn.model_validate(event(datetime.now(timezone.utc) + timedelta(minutes=1)))
    UsageIn.model_validate(event(datetime.now(timezone.utc) - timedelta(hours=23, minutes=59)))


@pytest.mark.parametrize("timestamp", [
    datetime.now(timezone.utc) + timedelta(minutes=10),
    datetime.now(timezone.utc) - timedelta(hours=24, seconds=5),
    datetime.now(),  # naive
])
def test_usage_rejects_future_stale_and_naive_timestamps(timestamp):
    with pytest.raises(ValidationError):
        UsageIn.model_validate(event(timestamp))


def test_usage_rejects_extra_fields_and_out_of_range_status():
    data = event(datetime.now(timezone.utc)); data["secret"] = "unexpected"
    with pytest.raises(ValidationError):
        UsageIn.model_validate(data)
    data = event(datetime.now(timezone.utc)); data["status_code"] = 600
    with pytest.raises(ValidationError):
        UsageIn.model_validate(data)


def test_usage_rejects_float_duration():
    data = event(datetime.now(timezone.utc)); data["duration_ms"] = 1.5
    with pytest.raises(ValidationError):
        UsageIn.model_validate(data)
