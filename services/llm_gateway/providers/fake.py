from __future__ import annotations

import uuid
from typing import Any, Dict, Tuple

from services.llm_gateway.providers.base import Provider


class FakeProvider(Provider):
    def __init__(self, name: str = "fake") -> None:
        super().__init__(name)

    def predict(self, prompt: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        extracted_table = prompt.get("extracted_table") or []
        if extracted_table and isinstance(extracted_table, list):
            lines = []
            for idx, row in enumerate(extracted_table, start=1):
                lines.append(
                    {
                        "line_no": idx,
                        "sku": row.get("SKU") or row.get("sku") or f"SKU-{idx}",
                        "description": row.get("Description") or row.get("description"),
                        "qty": row.get("Qty") or row.get("qty") or 1,
                        "uom": "ea",
                        "unit_price": row.get("unit_price") or 1.0,
                    }
                )
        else:
            lines = []
        order_id = prompt.get("order_id") or str(uuid.uuid4())
        result = {
            "order_draft": {
                "order_id": order_id,
                "po_number": None,
                "customer": {
                    "name": prompt.get("customer_hint"),
                    "vat": None,
                    "address": None,
                    "email": prompt.get("from_email"),
                },
                "delivery": {
                    "address": prompt.get("delivery_address"),
                    "date": prompt.get("delivery_date"),
                    "incoterm": None,
                },
                "currency": prompt.get("currency") or "EUR",
                "lines": lines,
                "totals": {"subtotal": None, "tax": None, "total": None},
            },
            "missing_fields": [],
            "anomalies": [],
            "email_draft": {
                "to": prompt.get("from_email"),
                "subject": "Order received",
                "body_text": "Automated draft generated.",
            },
            "confidence": 0.9,
        }
        usage = {"tokens_in": 100, "tokens_out": 200}
        return result, usage
