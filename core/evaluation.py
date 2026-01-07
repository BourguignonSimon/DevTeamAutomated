from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.failures import ContradictionError


@dataclass
class EvaluationResult:
    ok: bool
    alerts: List[str]


class OutcomeEvaluator:
    def __init__(self, *, max_minutes: int = 8 * 60, guard_unverifiable: bool = True):
        self.max_minutes = max_minutes
        self.guard_unverifiable = guard_unverifiable

    def evaluate(self, facts: List[Dict[str, Any]], deliverable: Dict[str, Any]) -> EvaluationResult:
        alerts: List[str] = []

        total_minutes = sum(f.get("value", 0) for f in facts if f.get("field") == "task_minutes")
        if total_minutes > self.max_minutes:
            alerts.append(f"total_minutes_exceeds_cap:{total_minutes}")

        if self.guard_unverifiable:
            if "claims" in deliverable:
                unverifiable = [c for c in deliverable.get("claims", []) if not c.get("sources")]
                if unverifiable:
                    raise ContradictionError("unverifiable claims detected")

        units = {f.get("provenance", {}).get("unit") for f in facts if f.get("provenance")}
        if None not in units and len(units) > 1:
            alerts.append("unit_mismatch")

        return EvaluationResult(ok=len(alerts) == 0, alerts=alerts)
