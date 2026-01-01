import json
import time
import uuid

from core.config import Settings
from core.event_utils import envelope
from core.schema_registry import load_registry
from core.stream_runtime import ReliableStreamProcessor


def _settings():
    return Settings(
        stream_name="runtime:events",
        dlq_stream="runtime:dlq",
        consumer_group="test_group",
        consumer_name="c1",
        block_ms=1,
        idle_reclaim_ms=1,
        reclaim_count=10,
        max_attempts=3,
        dedupe_ttl_s=100,
    )


def test_invalid_envelope_goes_to_dlq(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    proc = ReliableStreamProcessor(r, settings=_settings(), handler=lambda env: None, registry=reg)

    bad_env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": str(uuid.uuid4()), "request_text": ""},
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    bad_env.pop("timestamp")  # break envelope schema
    r.xadd(proc.settings.stream_name, {"event": json.dumps(bad_env)})

    proc.consume_once()

    assert r.xlen(proc.settings.dlq_stream) == 1
    assert r.xpending(proc.settings.stream_name, "test_group")["pending"] == 0


def test_retry_then_success(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    attempts = {"count": 0}

    def handler(env):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("fail")
        r.set("side_effect", attempts["count"])

    proc = ReliableStreamProcessor(r, settings=_settings(), handler=handler, registry=reg)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid request"},
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    r.xadd(proc.settings.stream_name, {"event": json.dumps(env)})

    # attempt 1 (fail)
    proc.consume_once()
    time.sleep(0.01)
    # attempt 2 (fail)
    proc.consume_once()
    time.sleep(0.01)
    # attempt 3 (success)
    proc.consume_once()

    assert r.get("side_effect") == attempts["count"]
    assert attempts["count"] == 3
    assert r.xpending(proc.settings.stream_name, "test_group")["pending"] == 0
    assert r.xlen(proc.settings.dlq_stream) == 0


def test_dlq_after_max_attempts(redis_client):
    r = redis_client
    reg = load_registry("schemas")

    def handler(env):
        raise RuntimeError("always fail")

    proc = ReliableStreamProcessor(r, settings=_settings(), handler=handler, registry=reg)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid"},
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    r.xadd(proc.settings.stream_name, {"event": json.dumps(env)})

    for _ in range(proc.settings.max_attempts + 1):
        proc.consume_once()
        time.sleep(0.01)

    assert r.xlen(proc.settings.dlq_stream) == 1
    assert r.xpending(proc.settings.stream_name, "test_group")["pending"] == 0


def test_idempotence_per_group(redis_client):
    r = redis_client
    reg = load_registry("schemas")
    counter = {"count": 0}

    def handler(env):
        counter["count"] += 1

    proc = ReliableStreamProcessor(r, settings=_settings(), handler=handler, registry=reg)

    event_id = str(uuid.uuid4())
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": str(uuid.uuid4()), "request_text": "valid req"},
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    env["event_id"] = event_id
    r.xadd(proc.settings.stream_name, {"event": json.dumps(env)})
    # duplicate with same event_id
    r.xadd(proc.settings.stream_name, {"event": json.dumps(env)})

    proc.consume_once()
    time.sleep(0.01)
    proc.consume_once()

    assert counter["count"] == 1
    assert r.xpending(proc.settings.stream_name, "test_group")["pending"] == 0
