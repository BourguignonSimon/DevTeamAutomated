from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.ingestion import load_excel


class ParsedOrder:
    def __init__(self, lines: List[Dict[str, Any]], missing_fields: List[Dict[str, str]], anomalies: List[Dict[str, Any]]):
        self.lines = lines
        self.missing_fields = missing_fields
        self.anomalies = anomalies


_SKU_HEADERS = ("sku", "item", "product")
_QTY_HEADERS = ("qty", "quantity", "qyt")
_DESC_HEADERS = ("description", "desc", "item description")


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _detect_columns(headers: List[str]) -> Tuple[int | None, int | None, int | None]:
    sku_idx = qty_idx = desc_idx = None
    normalized = [_normalize_header(h) for h in headers]
    for idx, h in enumerate(normalized):
        if sku_idx is None and any(tok in h for tok in _SKU_HEADERS):
            sku_idx = idx
        if qty_idx is None and any(tok in h for tok in _QTY_HEADERS):
            qty_idx = idx
        if desc_idx is None and any(tok in h for tok in _DESC_HEADERS):
            desc_idx = idx
    return sku_idx, qty_idx, desc_idx


def parse_excel_order(path: Path) -> ParsedOrder:
    rows = load_excel(path)
    if not rows:
        return ParsedOrder([], [{"field": "lines", "reason": "empty"}], [])

    headers = list(rows[0].keys())
    sku_idx, qty_idx, desc_idx = _detect_columns(headers)
    missing_fields: List[Dict[str, str]] = []
    if sku_idx is None:
        missing_fields.append({"field": "sku", "reason": "unable to detect sku column"})
    if qty_idx is None:
        missing_fields.append({"field": "qty", "reason": "unable to detect qty column"})

    lines: List[Dict[str, Any]] = []
    quantities: List[float] = []
    for _idx, row in enumerate(rows, start=1):
        values = list(row.values())
        sku = str(values[sku_idx]).strip() if sku_idx is not None and values[sku_idx] is not None else ""
        qty_raw = values[qty_idx] if qty_idx is not None and qty_idx < len(values) else None
        try:
            qty = float(qty_raw) if qty_raw not in (None, "") else 0
        except Exception:
            qty = 0
        desc = str(values[desc_idx]).strip() if desc_idx is not None and values[desc_idx] is not None else None
        if sku:
            lines.append({"line_no": len(lines) + 1, "sku": sku, "qty": qty, "description": desc})
            quantities.append(qty)
    anomalies: List[Dict[str, Any]] = []
    if quantities:
        median_qty = statistics.median([q for q in quantities if q is not None])
        for line in lines:
            if median_qty > 0 and line["qty"] > median_qty * 10:
                anomalies.append(
                    {
                        "type": "quantity_outlier",
                        "severity": "warning",
                        "description": f"qty {line['qty']} is high vs median {median_qty}",
                        "line_ref": line["line_no"],
                    }
                )
            if line["qty"] <= 0:
                missing_fields.append({"field": "qty", "reason": f"line {line['line_no']} has non-positive qty"})
    else:
        missing_fields.append({"field": "qty", "reason": "no quantities detected"})

    return ParsedOrder(lines, missing_fields, anomalies)
