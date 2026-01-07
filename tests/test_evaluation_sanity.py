import pytest

from core.evaluation import OutcomeEvaluator
from core.failures import ContradictionError


def test_evaluation_detects_over_cap():
    evaluator = OutcomeEvaluator(max_minutes=10)
    facts = [
        {"field": "task_minutes", "value": 6, "provenance": {}},
        {"field": "task_minutes", "value": 7, "provenance": {}},
    ]
    result = evaluator.evaluate(facts, deliverable={})
    assert not result.ok
    assert "total_minutes_exceeds_cap:13" in result.alerts


def test_evaluation_guardrails_unverifiable():
    evaluator = OutcomeEvaluator()
    facts = []
    with pytest.raises(ContradictionError):
        evaluator.evaluate(facts, {"claims": [{"text": "magic", "sources": []}]})
