from core.validators import DefinitionOfDoneRegistry, ValidationResult, default_validator


def test_registry_blocks_missing_evidence():
    reg = DefinitionOfDoneRegistry()
    result = reg.validate("dev_worker", {"project_id": "p", "backlog_item_id": "b", "evidence": {}})
    assert not result.ok


def test_default_validator_with_facts():
    payload = {"evidence": {"facts": [{"field": "task_minutes", "value": 1, "provenance": {}}], "deliverable": {}}}
    result = default_validator(payload)
    assert result.ok
