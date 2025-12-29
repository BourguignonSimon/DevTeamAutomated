import json
import uuid

import pytest

from core.event_utils import envelope
from core.schema_registry import load_registry
from core.backlog_store import BacklogStore
from core.redis_streams import ensure_consumer_group, read_group, ack
from tests.conftest import wait_for


STREAM = "audit:events"
DLQ = "audit:dlq"


def _clear_project(redis_client, project_id: str):
    # minimal cleanup for a project
    prefix = f"audit:project:{project_id}:backlog"
    keys = list(redis_client.scan_iter(match=f"{prefix}*"))
    if keys:
        redis_client.delete(*keys)


def test_envelope_missing_source_instance_goes_to_dlq(redis_client):
    bad = {
        "event_id": str(uuid.uuid4()),
        "event_type": "PROJECT.INITIAL_REQUEST_RECEIVED",
        "event_version": "1.0",
        "timestamp": "2025-01-01T00:00:00Z",
        "source": {"service": "tests"},  # instance missing
        "correlation_id": str(uuid.uuid4()),
        "causation_id": None,
        "payload": {"project_id": "p1", "request_text": "x"},
    }
    redis_client.xadd(STREAM, {"event": json.dumps(bad)})

    assert wait_for(lambda: redis_client.xlen(DLQ) > 0, timeout_s=6.0)
    doc = json.loads(redis_client.xrange(DLQ, count=1)[0][1]["dlq"])
    assert doc["event_type"] == "PROJECT.INITIAL_REQUEST_RECEIVED"
    assert doc["event_id"] == bad["event_id"]
    assert "instance" in doc["reason"]


def test_envelope_missing_event_id_goes_to_dlq(redis_client):
    bad = {
        "event_type": "PROJECT.INITIAL_REQUEST_RECEIVED",
        "event_version": "1.0",
        "timestamp": "2025-01-01T00:00:00Z",
        "source": {"service": "tests", "instance": "tests-1"},
        "correlation_id": str(uuid.uuid4()),
        "causation_id": None,
        "payload": {"project_id": "p2", "request_text": "x"},
    }
    redis_client.xadd(STREAM, {"event": json.dumps(bad)})

    assert wait_for(lambda: redis_client.xlen(DLQ) > 0, timeout_s=6.0)
    doc = json.loads(redis_client.xrange(DLQ, count=1)[0][1]["dlq"])
    assert doc["event_type"] is None or doc["event_type"] == "PROJECT.INITIAL_REQUEST_RECEIVED"
    assert "event_id" in doc["reason"]


def test_unknown_event_type_goes_to_dlq(redis_client):
    bad_env = envelope(
        event_type="NOT.A.REAL.EVENT",
        source="tests",
        payload={"foo": "bar"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(bad_env)})
    assert wait_for(lambda: redis_client.xlen(DLQ) > 0, timeout_s=6.0)
    doc = json.loads(redis_client.xrange(DLQ, count=1)[0][1]["dlq"])
    assert doc["event_type"] == "NOT.A.REAL.EVENT"
    assert "unknown event_type" in doc["reason"].lower()


def test_dlq_contains_required_fields(redis_client):
    # payload invalid to trigger DLQ
    bad_env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"request_text": "x"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(bad_env)})

    assert wait_for(lambda: redis_client.xlen(DLQ) > 0, timeout_s=6.0)
    doc = json.loads(redis_client.xrange(DLQ, count=1)[0][1]["dlq"])
    assert set(["event_id", "event_type", "reason", "original_event"]).issubset(doc.keys())
    assert doc["original_event"]["event_id"] == bad_env["event_id"]
    assert doc["original_event"]["event_type"] == bad_env["event_type"]


def test_idempotence_same_event_id_processed_once(redis_client):
    project_id = "idem-" + str(uuid.uuid4())[:8]
    store = BacklogStore(redis_client)
    _clear_project(redis_client, project_id)

    env1 = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": project_id, "request_text": "Need audit"},
        instance="tests-1",
    )
    # force same event_id twice
    env2 = dict(env1)

    redis_client.xadd(STREAM, {"event": json.dumps(env1)})
    redis_client.xadd(STREAM, {"event": json.dumps(env2)})

    def backlog_created():
        return len(store.list_item_ids(project_id)) > 0

    assert wait_for(backlog_created, timeout_s=8.0)
    ids1 = store.list_item_ids(project_id)
    timeboxed = wait_for(lambda: True, timeout_s=1.0)  # small pause for any duplicate work
    ids2 = store.list_item_ids(project_id)
    assert ids1 == ids2
