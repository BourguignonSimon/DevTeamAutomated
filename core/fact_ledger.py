from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable


class FactLedger:
    """Immutable append-only ledger stored under storage/audit_log by default.

    Each entry links outputs back to input facts and coefficients.
    """

    def __init__(self, base_dir: str | None = None):
        resolved_dir = base_dir or os.getenv("LEDGER_DIR", "storage/audit_log")
        self.base_dir = Path(resolved_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def record(self, project_id: str, backlog_item_id: str, facts: Iterable[Dict[str, Any]], coefficients: Dict[str, Any] | None = None) -> Path:
        entry = {
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "facts": list(facts),
            "coefficients": coefficients or {},
        }
        path = self.base_dir / f"{project_id}_ledger.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return path

    def load_entries(self, project_id: str) -> list[Dict[str, Any]]:
        path = self.base_dir / f"{project_id}_ledger.jsonl"
        if not path.exists():
            return []
        entries: list[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                entries.append(json.loads(line))
        return entries
