import json
import uuid

from core.event_utils import envelope
from tests.conftest import wait_for


def test_completed_without_evidence_goes_to_dlq(redis_client):
    project_id = str(uuid.uuid4())
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        event_version=1,
        source="tests",
        payload={"project_id": project_id, "request_text": "x"},
    )
    redis_client.xadd("audit:events", {"event": json.dumps(env)})

    def find_dispatched():
        events = redis_client.xrange("audit:events", min="-", max="+")
        for _, fields in events:
            if "event" not in fields:
                continue
            ev = json.loads(fields["event"])
            if ev.get("event_type") == "WORK.ITEM_DISPATCHED":
                return ev
        return None

    assert wait_for(lambda: find_dispatched() is not None, timeout_s=6.0)
    dispatched = find_dispatched()
    item_id = dispatched["payload"]["backlog_item_id"]

    # Missing required evidence in schema -> should end in DLQ
    bad_completed = envelope(
        event_type="WORK.ITEM_COMPLETED",
        event_version=1,
        source="tests",
        payload={"project_id": project_id, "backlog_item_id": item_id},
        correlation_id=dispatched["correlation_id"],
        causation_id=dispatched["event_id"],
    )
    redis_client.xadd("audit:events", {"event": json.dumps(bad_completed)})

    assert wait_for(lambda: redis_client.xlen("audit:dlq") > 0, timeout_s=6.0)
    dlq_item = redis_client.xrevrange("audit:dlq", count=1)[0]
    doc = json.loads(dlq_item[1]["dlq"])
    assert "evidence" in doc["reason"]
