from __future__ import annotations

import csv
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List

import redis

from core.event_utils import envelope, now_iso
from core.locks import acquire_lock, release_lock
from core.logging import setup_logging
from core.schema_registry import load_registry
from core.schema_validate import validate_payload
from core.stream_runtime import ReliableStreamProcessor
from services.order_intake_agent.parser import parse_excel_order
from services.order_intake_agent.settings import OrderIntakeSettings
from services.order_intake_agent.store import OrderStore

log = logging.getLogger(__name__)


class OrderIntakeAgent:
    def __init__(self, r: redis.Redis, settings: OrderIntakeSettings):
        self.r = r
        self.settings = settings
        self.registry = load_registry("/app/schemas")
        self.store = OrderStore(r, storage_dir=settings.storage_dir)
        self.processor = ReliableStreamProcessor(
            r,
            settings=settings,
            handler=self.handle_event,
            registry=self.registry,
        )

    def run(self) -> None:  # pragma: no cover - runtime entrypoint
        setup_logging(self.settings.log_level)
        self.processor.run_forever()

    # Handlers
    def handle_event(self, env: Dict[str, Any]) -> None:
        event_type = env.get("event_type")
        if event_type == "ORDER.INBOX_RECEIVED":
            self._handle_inbox(env)
        elif event_type == "ORDER.VALIDATED":
            self._handle_validated(env)

    def _load_lines(self, order_id: str, attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
        missing_fields: List[Dict[str, str]] = []
        anomalies: List[Dict[str, Any]] = []
        lines: List[Dict[str, Any]] = []

        for att in attachments:
            metadata = self.store.get_artifact_metadata(att["artifact_id"])
            if not metadata:
                missing_fields.append({"field": "attachment", "reason": f"artifact {att['artifact_id']} missing"})
                continue
            path = Path(metadata["path"])
            if att["mime_type"].endswith("excel") or att["filename"].lower().endswith(".xlsx"):
                parsed = parse_excel_order(path)
                lines.extend(parsed.lines)
                missing_fields.extend(parsed.missing_fields)
                anomalies.extend(parsed.anomalies)
            elif att["mime_type"].endswith("pdf") or att["filename"].lower().endswith(".pdf"):
                missing_fields.append({"field": "order_details", "reason": "pdf requires manual input"})
            else:
                missing_fields.append({"field": "order_details", "reason": f"unsupported mime {att['mime_type']}"})

        return {"lines": lines, "missing_fields": missing_fields, "anomalies": anomalies}

    def _build_email_draft(self, from_email: str, missing_fields: List[Dict[str, Any]]) -> Dict[str, str]:
        if missing_fields:
            body = "We received your order but need the following details:\n" + "\n".join(
                f"- {m['field']}: {m['reason']}" for m in missing_fields
            )
            subject = "Need information to complete your order"
        else:
            body = "Thank you for your order. Please confirm the attached summary."
            subject = "Order received"
        return {"to": from_email, "subject": subject, "body_text": body}

    def _persist_and_emit(self, env: Dict[str, Any], order_draft: Dict[str, Any], missing_fields: List[Dict[str, Any]], anomalies: List[Dict[str, Any]]):
        order_id = order_draft["order_id"]
        self.store.save_order_draft(order_id, order_draft)
        self.store.save_missing_fields(order_id, missing_fields)
        self.store.save_anomalies(order_id, anomalies)

        email_draft = self._build_email_draft(env["payload"]["from_email"], missing_fields)
        draft_env = envelope(
            event_type="ORDER.DRAFT_CREATED",
            payload={"order_id": order_id, "order_draft": order_draft, "email_draft": email_draft},
            source=self.settings.service_name,
            correlation_id=env.get("correlation_id"),
            causation_id=env.get("event_id"),
        )
        self.r.xadd(self.settings.stream_name, {"event": json.dumps(draft_env)})

        if missing_fields:
            missing_env = envelope(
                event_type="ORDER.MISSING_FIELDS_DETECTED",
                payload={"order_id": order_id, "missing_fields": missing_fields},
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(missing_env)})
            validation_env = envelope(
                event_type="ORDER.VALIDATION_REQUIRED",
                payload={"order_id": order_id, "reason": "missing_fields"},
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.store.add_pending_validation(self.settings.validation_set_key, order_id)
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(validation_env)})
            question_id = str(uuid.uuid4())
            question_env = envelope(
                event_type="QUESTION.CREATED",
                payload={
                    "question": {
                        "id": question_id,
                        "project_id": order_id,
                        "backlog_item_id": order_id,
                        "question_text": "Provide missing order details",
                        "answer_type": "text",
                        "status": "OPEN",
                        "correlation_id": env.get("correlation_id"),
                    }
                },
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(question_env)})
            clarification_env = envelope(
                event_type="CLARIFICATION.NEEDED",
                payload={
                    "project_id": order_id,
                    "backlog_item_id": order_id,
                    "reason": "order_missing_fields",
                    "missing_fields": [m["field"] for m in missing_fields],
                    "agent": self.settings.service_name,
                },
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(clarification_env)})
        if anomalies:
            anomaly_env = envelope(
                event_type="ORDER.ANOMALY_DETECTED",
                payload={"order_id": order_id, "anomalies": anomalies},
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(anomaly_env)})
            validation_env = envelope(
                event_type="ORDER.VALIDATION_REQUIRED",
                payload={"order_id": order_id, "reason": "anomalies"},
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.store.add_pending_validation(self.settings.validation_set_key, order_id)
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(validation_env)})

        if not missing_fields and not anomalies:
            self._export_and_publish(order_id, order_draft, email_draft, env)

    def _handle_inbox(self, env: Dict[str, Any]) -> None:
        payload = env["payload"]
        res_pl = validate_payload(self.registry, env["event_type"], payload)
        if not res_pl.ok:
            raise ValueError(res_pl.error or "invalid payload")

        order_id = payload["order_id"]
        if self.store.get_order_draft(order_id):
            log.info("order %s already processed", order_id)
            return

        parsed = self._load_lines(order_id, payload.get("attachments", []))
        delivery = {
            "address": payload.get("delivery_address"),
            "date": payload.get("delivery_date"),
            "incoterm": None,
        }
        order_draft = {
            "order_id": order_id,
            "po_number": None,
            "customer": {"name": payload.get("customer_hint"), "vat": None, "address": None, "email": payload.get("from_email")},
            "delivery": delivery,
            "currency": "EUR",
            "lines": parsed["lines"],
            "totals": {"subtotal": None, "tax": None, "total": None},
        }

        missing_fields = list(parsed["missing_fields"])
        if not delivery.get("address"):
            missing_fields.append({"field": "delivery.address", "reason": "missing delivery address"})
        if not delivery.get("date"):
            missing_fields.append({"field": "delivery.date", "reason": "missing delivery date"})

        anomalies = parsed["anomalies"]

        self._persist_and_emit(env, order_draft, missing_fields, anomalies)

    def _export_and_publish(self, order_id: str, order_draft: Dict[str, Any], email_draft: Dict[str, str], env: Dict[str, Any]) -> None:
        lock = acquire_lock(self.r, f"order:{order_id}:export", ttl_ms=self.settings.export_lock_ttl_ms)
        if not lock:
            log.info("export lock busy for %s", order_id)
            return
        try:
            export_path = self.store.export_path(order_id)
            with export_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["line_no", "sku", "description", "qty", "uom", "unit_price"])
                for line in order_draft.get("lines", []):
                    writer.writerow([
                        line.get("line_no"),
                        line.get("sku"),
                        line.get("description"),
                        line.get("qty"),
                        line.get("uom"),
                        line.get("unit_price"),
                    ])
            artifact_id = str(uuid.uuid4())
            export_meta = {"artifact_id": artifact_id, "path": str(export_path), "format": "csv"}
            self.store.record_export(order_id, export_meta)
            export_env = envelope(
                event_type="ORDER.EXPORT_READY",
                payload={"order_id": order_id, "export": {"artifact_id": artifact_id, "format": "csv"}, "email_draft": email_draft},
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(export_env)})

            deliverable_env = envelope(
                event_type="DELIVERABLE.PUBLISHED",
                payload={
                    "project_id": order_id,
                    "backlog_item_id": order_id,
                    "deliverable": {
                        "type": "order_export",
                        "content": {"artifact_id": artifact_id, "email_draft": email_draft},
                        "timestamp": now_iso(),
                        "confidence": 0.9,
                        "project_id": order_id,
                        "backlog_item_id": order_id,
                    },
                },
                source=self.settings.service_name,
                correlation_id=env.get("correlation_id"),
                causation_id=env.get("event_id"),
            )
            self.r.xadd(self.settings.stream_name, {"event": json.dumps(deliverable_env)})
        finally:
            release_lock(self.r, lock)

    def _handle_validated(self, env: Dict[str, Any]) -> None:
        payload = env["payload"]
        res_pl = validate_payload(self.registry, env["event_type"], payload)
        if not res_pl.ok:
            raise ValueError(res_pl.error or "invalid payload")
        order_id = payload["order_id"]
        draft = payload.get("final_order_draft") or self.store.get_order_draft(order_id)
        if not draft:
            raise ValueError("missing draft for validated order")
        email_draft = self._build_email_draft(draft.get("customer", {}).get("email") or payload.get("validated_by", ""), [])
        self.store.remove_pending_validation(self.settings.validation_set_key, order_id)
        self._export_and_publish(order_id, draft, email_draft, env)


def run() -> None:  # pragma: no cover - entrypoint
    settings = OrderIntakeSettings()
    setup_logging(settings.log_level)
    r = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)
    agent = OrderIntakeAgent(r, settings)
    agent.run()


if __name__ == "__main__":  # pragma: no cover
    run()
