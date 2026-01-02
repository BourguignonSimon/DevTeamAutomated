import json
import uuid
from pathlib import Path

import pytest
from openpyxl import Workbook

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
        llm_gateway_url="http://fake-gateway",
        llm_provider_order=("fake",),
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


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def gateway_payload_success():
    return {
        "ok": True,
        "provider_used": "fake",
        "result_json": {
            "order_draft": {
                "order_id": "",
                "po_number": None,
                "customer": {"name": "", "vat": None, "address": None, "email": "user@example.com"},
                "delivery": {"address": "123 street", "date": "2024-01-02", "incoterm": None},
                "currency": "EUR",
                "lines": [{"line_no": 1, "sku": "SKU-1", "description": "Widget", "qty": 5, "uom": "ea", "unit_price": 1.0}],
                "totals": {"subtotal": None, "tax": None, "total": None},
            },
            "missing_fields": [],
            "anomalies": [],
            "email_draft": {"to": "user@example.com", "subject": "Order", "body_text": "text"},
        },
    }


@pytest.fixture
def patch_gateway(monkeypatch):
    def _patch(payload):
        def fake_post(url, json=None, timeout=None):
            return DummyResponse(payload)

        monkeypatch.setattr("httpx.post", fake_post)

    return _patch


def test_human_approval_required(redis_client, order_settings, tmp_path, patch_gateway, gateway_payload_success):
    patch_gateway(gateway_payload_success)
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
    assert "ORDER.EXPORT_READY" not in event_types
    assert "DELIVERABLE.PUBLISHED" not in event_types
    assert order_id in agent.store.list_pending_validation(order_settings.validation_set_key)

    validate_resp = client.post(
        f"/orders/{order_id}/validate",
        json={},
    )
    assert validate_resp.status_code == 200

    _process_all(agent)
    event_types = _collect_event_types(redis_client)
    assert "ORDER.VALIDATED" in event_types
    assert "ORDER.EXPORT_READY" in event_types
    assert "DELIVERABLE.PUBLISHED" in event_types


def test_gateway_outage_triggers_manual_review(redis_client, order_settings, tmp_path, monkeypatch):
    def failing_post(url, json=None, timeout=None):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("httpx.post", failing_post)
    deps = Dependencies(order_settings, redis_client)
    client = get_test_client(deps)
    excel = tmp_path / "order.xlsx"
    _create_excel(excel, [["SKU-2", 2, "Gadget"]])

    resp = client.post(
        "/orders/inbox",
        files={"files": ("order.xlsx", excel.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"from_email": "user@example.com", "subject": "New order"},
    )
    order_id = resp.json()["order_id"]

    agent = OrderIntakeAgent(redis_client, order_settings)
    _process_all(agent)

    missing = agent.store.get_missing_fields(order_id)
    assert any(m.get("field") == "gateway" for m in missing)
    event_types = _collect_event_types(redis_client)
    assert "ORDER.EXPORT_READY" not in event_types
