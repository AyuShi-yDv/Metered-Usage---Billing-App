from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.schemas import UsageIn

def event(timestamp):
    return {"event_id":str(uuid4()),"endpoint":"/v1/test","timestamp":timestamp.isoformat(),"duration_ms":10,"status_code":200}

def test_usage_accepts_utc_and_offsets():
    parsed=UsageIn.model_validate(event(datetime.now(timezone.utc)))
    assert parsed.timestamp.tzinfo is not None

@pytest.mark.parametrize("timestamp",[datetime.now(timezone.utc)+timedelta(minutes=1),datetime.now(timezone.utc)-timedelta(hours=24,seconds=1),datetime.now()])
def test_usage_rejects_future_stale_and_naive_timestamps(timestamp):
    with pytest.raises(ValidationError): UsageIn.model_validate(event(timestamp))

def test_usage_rejects_extra_fields_and_invalid_status():
    data=event(datetime.now(timezone.utc)); data["secret"]="unexpected"
    with pytest.raises(ValidationError): UsageIn.model_validate(data)
    data=event(datetime.now(timezone.utc)); data["status_code"]=599
    # 599 is inside the permitted HTTP status numeric range.
    assert UsageIn.model_validate(data).status_code==599
