from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Dict, Optional


class FailureCategory(str, enum.Enum):
    TOOL_FAILURE = "TOOL_FAILURE"
    DATA_INSUFFICIENCY = "DATA_INSUFFICIENCY"
    REASONING_CONTRADICTION = "REASONING_CONTRADICTION"


@dataclass
class Failure:
    category: FailureCategory
    reason: str
    details: Optional[Dict[str, Any]] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = {"category": self.category.value, "reason": self.reason}
        if self.details:
            payload["details"] = self.details
        return payload


class MissingDataError(ValueError):
    def __init__(self, fields: list[str]):
        super().__init__("missing critical fields: " + ",".join(fields))
        self.fields = fields
        self.failure = Failure(FailureCategory.DATA_INSUFFICIENCY, str(self))


class ContradictionError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.failure = Failure(FailureCategory.REASONING_CONTRADICTION, message)
