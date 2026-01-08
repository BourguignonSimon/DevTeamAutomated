import json
import uuid

import pytest

from core.backlog_store import BacklogStore
from core.config import Settings
from core.event_utils import envelope, now_iso
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload
from core.state_machine import BacklogStatus, IllegalTransition, assert_transition
from core.stream_runtime import ReliableStreamProcessor
from core.question_store import QuestionStore
from services.orchestrator.main import process_message


def _settings(**overrides) -> Settings:
    base = {
        "stream_name": "verify:events",
        "dlq_stream": "verify:dlq",
        "consumer_group": "verify_group",
        "consumer_name": "verify-1",
        "block_ms": 1,
        "idle_reclaim_ms": 0,
        "reclaim_count": 10,
        "max_attempts": 2,
        "dedupe_ttl_s": 60,
    }
    base.update(overrides)
    return Settings(**base)


def _dispatch_payload(project_id: str, backlog_item_id: str) -> dict:
    return {
        "project_id": project_id,
        "backlog_item_id": backlog_item_id,
        "item_type": "AGENT_TASK",
        "agent_target": "time_waste_worker",
        "work_context": {"rows": [{"estimated_minutes": 12, "category": "ops", "text": "triage"}]},
    }


def _deliverable_payload(project_id: str, backlog_item_id: str) -> dict:
    return {
        "project_id": project_id,
        "backlog_item_id": backlog_item_id,
        "deliverable": {
            "type": "summary",
            "content": {"summary": "ok"},
            "timestamp": now_iso(),
            "confidence": 0.9,
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
        },
    }


def test_schema_validation_valid_payloads():
    reg = load_registry("schemas")
    project_id = str(uuid.uuid4())
    backlog_item_id = str(uuid.uuid4())

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": project_id, "request_text": "full audit"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    assert validate_envelope(reg, env).ok
    assert validate_payload(reg, "PROJECT.INITIAL_REQUEST_RECEIVED", env["payload"]).ok

    dispatch_payload = _dispatch_payload(project_id, backlog_item_id)
    assert validate_payload(reg, "WORK.ITEM_DISPATCHED", dispatch_payload).ok

    deliverable_payload = _deliverable_payload(project_id, backlog_item_id)
    assert validate_payload(reg, "DELIVERABLE.PUBLISHED", deliverable_payload).ok


def test_schema_validation_invalid_envelope():
    reg = load_registry("schemas")
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": str(uuid.uuid4()), "request_text": "full audit"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    env.pop("timestamp")
    assert not validate_envelope(reg, env).ok


def test_dlq_routing_does_not_block_valid_events(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    counter = {"count": 0}

    def handler(env):
        counter["count"] += 1

    settings = _settings()
    proc = ReliableStreamProcessor(r, settings=settings, handler=handler, registry=reg)

    bad_env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": str(uuid.uuid4())},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    good_env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )

    r.xadd(settings.stream_name, {"event": json.dumps(bad_env)})
    r.xadd(settings.stream_name, {"event": json.dumps(good_env)})

    proc.consume_once()

    assert counter["count"] == 1
    assert r.xlen(settings.dlq_stream) == 1
    assert r.xpending(settings.stream_name, settings.consumer_group)["pending"] == 0


def test_retry_pending_reclaim_and_dlq(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    attempts = {"count": 0}

    def handler(env):
        attempts["count"] += 1
        raise RuntimeError("fail")

    settings = _settings(max_attempts=2, idle_reclaim_ms=0)
    proc = ReliableStreamProcessor(r, settings=settings, handler=handler, registry=reg)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    r.xadd(settings.stream_name, {"event": json.dumps(env)})

    proc.consume_once()
    assert r.xpending(settings.stream_name, settings.consumer_group)["pending"] == 1

    proc.consume_once()
    assert attempts["count"] == 2
    assert r.xlen(settings.dlq_stream) == 1
    assert r.xpending(settings.stream_name, settings.consumer_group)["pending"] == 0


def test_state_machine_illegal_transition():
    with pytest.raises(IllegalTransition):
        assert_transition(BacklogStatus.READY, BacklogStatus.DONE, item_id="item-1")


def test_idempotence_per_consumer_group(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    counter = {"count": 0}

    def handler(env):
        counter["count"] += 1

    settings = _settings(consumer_group="verify_idem")
    proc = ReliableStreamProcessor(r, settings=settings, handler=handler, registry=reg)

    event_id = str(uuid.uuid4())
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    env["event_id"] = event_id
    r.xadd(settings.stream_name, {"event": json.dumps(env)})
    r.xadd(settings.stream_name, {"event": json.dumps(env)})

    proc.consume_once()
    proc.consume_once()

    assert counter["count"] == 1


def test_clarification_loop_with_orchestrator(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    settings = _settings(stream_name="verify:events", dlq_stream="verify:dlq", consumer_group="verify_orch")
    r.xgroup_create(settings.stream_name, settings.consumer_group, mkstream=True)

    store = BacklogStore(r, prefix=settings.key_prefix)
    qstore = QuestionStore(r, prefix=settings.key_prefix)

    project_id = str(uuid.uuid4())
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        payload={"project_id": project_id, "request_text": "kpi"},
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )

    process_message(
        r,
        reg,
        store,
        qstore,
        settings,
        settings.consumer_group,
        "1-0",
        {"event": json.dumps(env)},
    )

    events = [json.loads(fields["event"]) for _mid, fields in r.xrange(settings.stream_name)]
    event_types = {e["event_type"] for e in events}
    assert "QUESTION.CREATED" in event_types
    assert "CLARIFICATION.NEEDED" in event_types

    open_questions = qstore.list_open(project_id)
    assert open_questions
    question_id = open_questions[0]
    question = qstore.get_question(project_id, question_id)
    item_id = question["backlog_item_id"]
    item = store.get_item(project_id, item_id)
    assert item["status"] == BacklogStatus.BLOCKED.value

    answer_env = envelope(
        event_type="USER.ANSWER_SUBMITTED",
        payload={"project_id": project_id, "question_id": question_id, "answer": "answer"},
        source="tests",
        correlation_id=env["correlation_id"],
        causation_id=env["event_id"],
    )
    process_message(
        r,
        reg,
        store,
        qstore,
        settings,
        settings.consumer_group,
        "2-0",
        {"event": json.dumps(answer_env)},
    )

    item = store.get_item(project_id, item_id)
    assert item["status"] in {BacklogStatus.READY.value, BacklogStatus.IN_PROGRESS.value}

    events = [json.loads(fields["event"]) for _mid, fields in r.xrange(settings.stream_name)]
    event_types = {e["event_type"] for e in events}
    assert "BACKLOG.ITEM_UNBLOCKED" in event_types
