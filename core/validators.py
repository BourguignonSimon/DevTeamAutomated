from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from core.evaluation import OutcomeEvaluator


@dataclass
class ValidationResult:
    ok: bool
    reason: str | None = None


class DefinitionOfDoneRegistry:
    def __init__(self):
        self._registry: Dict[str, Callable[[dict], ValidationResult]] = {}
        self.evaluator = OutcomeEvaluator()

    def register(self, agent_name: str, validator: Callable[[dict], ValidationResult]) -> None:
        self._registry[agent_name] = validator

    def validate(self, agent_name: str, payload: dict) -> ValidationResult:
        validator = self._registry.get(agent_name)
        if not validator:
            evidence = payload.get("evidence") or {}
            if evidence:
                return ValidationResult(True)
            return ValidationResult(False, "missing evidence")
        return validator(payload)


def default_validator(payload: dict) -> ValidationResult:
    evidence = payload.get("evidence") or {}
    if not evidence:
        return ValidationResult(False, "missing evidence")
    facts = evidence.get("facts", [])
    deliverable = evidence.get("deliverable", {})
    result = OutcomeEvaluator().evaluate(facts, deliverable)
    if not result.ok:
        return ValidationResult(False, ";".join(result.alerts))
    return ValidationResult(True)
