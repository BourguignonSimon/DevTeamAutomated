from core.fact_ledger import FactLedger


def test_fact_ledger_integrity(tmp_path):
    ledger = FactLedger(base_dir=tmp_path)
    facts = [
        {"id": "f1", "field": "task_minutes", "value": 10, "provenance": {"row_id": "r1", "source_fields": ["text"]}},
        {"id": "f2", "field": "task_text", "value": "demo", "provenance": {"row_id": "r1", "source_fields": ["text"]}},
    ]
    ledger.record("p1", "b1", facts, coefficients={"weight": 1.0})
    entries = ledger.load_entries("p1")
    assert entries[0]["coefficients"]["weight"] == 1.0
    assert entries[0]["facts"][0]["id"] == "f1"
