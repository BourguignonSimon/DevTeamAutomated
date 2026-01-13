from core.failures import Failure, FailureCategory


def test_failure_payload_structure():
    failure = Failure(FailureCategory.TOOL_FAILURE, "timeout", details={"tool": "llm"})
    payload = failure.to_payload()
    assert payload["category"] == "TOOL_FAILURE"
    assert payload["details"]["tool"] == "llm"
