from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List

from core.failures import MissingDataError
from core.fact_ledger import FactLedger


@dataclass
class Fact:
    id: str
    field: str
    value: Any
    provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class Facts:
    facts: List[Fact]

    def to_records(self) -> List[Dict[str, Any]]:
        return [f.to_dict() for f in self.facts]


class GroundingEngine:
    def __init__(self, ledger: FactLedger | None = None):
        self.ledger = ledger or FactLedger()

    def extract(self, *, project_id: str, backlog_item_id: str, rows: Iterable[Dict[str, Any]]) -> Facts:
        rows = list(rows)
        if not rows:
            raise MissingDataError(["rows"])

        facts: List[Fact] = []
        for idx, row in enumerate(rows):
            if "text" not in row or "estimated_minutes" not in row:
                missing = [k for k in ("text", "estimated_minutes") if k not in row]
                raise MissingDataError(missing)
            prov = {"row_id": row.get("id", idx), "source_fields": list(row.keys())}
            facts.append(
                Fact(
                    id=f"fact-{idx}",
                    field="task_minutes",
                    value=row["estimated_minutes"],
                    provenance=prov,
                )
            )
            facts.append(
                Fact(
                    id=f"fact-text-{idx}",
                    field="task_text",
                    value=row["text"],
                    provenance=prov,
                )
            )

        self.ledger.record(project_id, backlog_item_id, [f.to_dict() for f in facts], coefficients={"count": len(facts)})
        return Facts(facts)
