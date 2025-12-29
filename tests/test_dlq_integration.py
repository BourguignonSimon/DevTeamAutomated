import json

from core.event_utils import envelope
from tests.conftest import wait_for


def test_invalid_event_goes_to_dlq(redis_client):
    # Missing required fields in payload (project_id)
    bad_env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"request_text": "x"},
        instance="tests-1",
    )
    redis_client.xadd("audit:events", {"event": json.dumps(bad_env)})

    def has_dlq():
        return redis_client.xlen("audit:dlq") > 0

    assert wait_for(has_dlq, timeout_s=6.0)
    items = redis_client.xrange("audit:dlq", count=1)
    assert items
    doc = json.loads(items[0][1]["dlq"])
    assert "project_id" in doc["reason"]
