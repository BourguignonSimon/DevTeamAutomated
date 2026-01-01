import json
import uuid
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.event_utils import envelope
from services.order_intake_agent.app import Dependencies, get_test_client
from services.order_intake_agent.processor import OrderIntakeAgent
from services.order_intake_agent.settings import OrderIntakeSettings


@pytest.fixture
def order_settings(tmp_path):
    return OrderIntakeSettings(
        stream_name="audit:events",
        dlq_stream="audit:dlq",
        consumer_group=f"order-intake-{uuid.uuid4()}",
        consumer_name="test-consumer",
        storage_dir=str(tmp_path / "storage"),
        log_level="DEBUG",
    )


def _create_excel(path: Path, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "Qty", "Description"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def _collect_event_types(r):
    return [json.loads(fields["event"])["event_type"] for _, fields in r.xrange("audit:events")]


def _process_all(agent: OrderIntakeAgent):
    processed = 1
    while processed:
        processed = agent.processor.consume_once()


def test_happy_path_excel_to_export(redis_client, order_settings, tmp_path):
    deps = Dependencies(order_settings, redis_client)
    client = get_test_client(deps)
    excel = tmp_path / "order.xlsx"
    _create_excel(excel, [["SKU-1", 5, "Widget"]])

    resp = client.post(
        "/orders/inbox",
        files={"files": ("order.xlsx", excel.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"from_email": "user@example.com", "subject": "New order", "delivery_address": "123 street", "delivery_date": "2024-01-02"},
    )
    assert resp.status_code == 200
    order_id = resp.json()["order_id"]

    agent = OrderIntakeAgent(redis_client, order_settings)
    _process_all(agent)

    event_types = _collect_event_types(redis_client)
    assert "ORDER.DRAFT_CREATED" in event_types
    assert "ORDER.EXPORT_READY" in event_types
    assert "DELIVERABLE.PUBLISHED" in event_types

    draft = agent.store.get_order_draft(order_id)
    assert draft["lines"]
    export_meta = agent.store.get_export(order_id)
    assert export_meta is not None
    assert Path(export_meta["path"]).exists()


def test_missing_fields_and_validation_loop(redis_client, order_settings, tmp_path):
    deps = Dependencies(order_settings, redis_client)
    client = get_test_client(deps)
    excel = tmp_path / "order.xlsx"
    _create_excel(excel, [["SKU-2", 2, "Gadget"]])

    resp = client.post(
        "/orders/inbox",
        files={"files": ("order.xlsx", excel.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"from_email": "user@example.com", "subject": "Missing delivery"},
    )
    order_id = resp.json()["order_id"]

    agent = OrderIntakeAgent(redis_client, order_settings)
    _process_all(agent)

    event_types = _collect_event_types(redis_client)
    assert "ORDER.MISSING_FIELDS_DETECTED" in event_types
    assert "ORDER.VALIDATION_REQUIRED" in event_types

    validate_resp = client.post(
        f"/orders/{order_id}/validate",
        json={"delivery": {"address": "123 street", "date": "2024-01-02"}},
    )
    assert validate_resp.status_code == 200

    _process_all(agent)
    event_types = _collect_event_types(redis_client)
    assert "ORDER.VALIDATED" in event_types
    assert "ORDER.EXPORT_READY" in event_types


def test_idempotent_inbox(redis_client, order_settings, tmp_path):
    agent = OrderIntakeAgent(redis_client, order_settings)
    env = envelope(
        event_type="ORDER.INBOX_RECEIVED",
        payload={
            "order_id": str(uuid.uuid4()),
            "from_email": "user@example.com",
            "subject": "dup",
            "received_at": "2024-01-01T00:00:00Z",
            "attachments": [],
        },
        source="test",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    redis_client.xadd("audit:events", {"event": json.dumps(env)})
    redis_client.xadd("audit:events", {"event": json.dumps(env)})

    _process_all(agent)
    event_types = _collect_event_types(redis_client)
    assert event_types.count("ORDER.DRAFT_CREATED") == 1


def test_invalid_payload_goes_dlq(redis_client, order_settings):
    agent = OrderIntakeAgent(redis_client, order_settings)
    bad_env = envelope(
        event_type="ORDER.INBOX_RECEIVED",
        payload={"order_id": str(uuid.uuid4()), "subject": "bad", "received_at": "2024-01-01T00:00:00Z", "attachments": []},
        source="test",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    redis_client.xadd("audit:events", {"event": json.dumps(bad_env)})
    _process_all(agent)
    entries = redis_client.xrange("audit:dlq")
    assert entries
    last = json.loads(entries[-1][1]["dlq"])
    assert "required property" in last.get("reason", "")


def test_export_lock_ownership(redis_client, order_settings, tmp_path):
    agent = OrderIntakeAgent(redis_client, order_settings)
    order_id = str(uuid.uuid4())
    draft = {
        "order_id": order_id,
        "lines": [{"line_no": 1, "sku": "SKU", "qty": 1}],
        "customer": {"email": "user@example.com"},
        "delivery": {},
        "currency": "EUR",
        "totals": {},
    }
    agent.store.save_order_draft(order_id, draft)
    held = redis_client.set(f"order:{order_id}:export", "foreign", nx=True, px=order_settings.export_lock_ttl_ms)
    agent._export_and_publish(order_id, draft, {"to": "user@example.com", "subject": "s", "body_text": "b"}, {"event_id": "x", "correlation_id": "c"})
    assert redis_client.get(f"order:{order_id}:export") == "foreign"

    redis_client.delete(f"order:{order_id}:export")
    agent._export_and_publish(order_id, draft, {"to": "user@example.com", "subject": "s", "body_text": "b"}, {"event_id": "x", "correlation_id": "c"})
    assert redis_client.get(f"order:{order_id}:export") is None
