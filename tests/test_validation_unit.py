import json

from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload


def test_validate_envelope_ok():
    reg = load_registry("/app/schemas")
    env = {
        "event_id": "00000000-0000-0000-0000-000000000001",
        "event_type": "PROJECT.INITIAL_REQUEST_RECEIVED",
        "event_version": 1,
        "timestamp": "2025-01-01T00:00:00Z",
        "correlation_id": "00000000-0000-0000-0000-000000000002",
        "causation_id": None,
        "source": {"service": "tests", "instance": "tests-1"},
        "payload": {"project_id": "00000000-0000-0000-0000-000000000010", "request_text": "x"},
    }
    res = validate_envelope(reg, env)
    assert res.ok


def test_validate_payload_ok():
    reg = load_registry("/app/schemas")
    payload = {"project_id": "00000000-0000-0000-0000-000000000010", "request_text": "x"}
    res = validate_payload(reg, "PROJECT.INITIAL_REQUEST_RECEIVED", payload)
    assert res.ok


def test_validate_payload_missing_required_field():
    reg = load_registry("/app/schemas")
    payload = {"request_text": "x"}
    res = validate_payload(reg, "PROJECT.INITIAL_REQUEST_RECEIVED", payload)
    assert not res.ok
    assert "project_id" in (res.error or "")
