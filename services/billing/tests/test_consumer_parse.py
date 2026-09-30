import json
from uuid import uuid4

import pytest

from app.consumer import InvalidMessage, parse_message


def body(**over):
    data = {"schema_version": 1, "event_id": str(uuid4()), "account_id": str(uuid4()), "endpoint": "/v1/x",
            "timestamp": "2026-01-01T10:00:00+00:00", "duration_ms": 12, "status_code": 200}
    data.update(over)
    return json.dumps(data).encode()


def test_valid_message_is_parsed():
    parsed = parse_message(body())
    assert parsed["status"] == 200 and parsed["occurred"].tzinfo is not None


@pytest.mark.parametrize("raw", [
    b"not json", b"[]", body(schema_version=2), body(status_code=700), body(duration_ms=-1),
    body(timestamp="2026-01-01T10:00:00"), body(event_id="nope"),
])
def test_bad_messages_are_permanent_failures(raw):
    with pytest.raises(InvalidMessage):
        parse_message(raw)
