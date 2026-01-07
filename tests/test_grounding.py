import json
from pathlib import Path

import pytest

from core.fact_ledger import FactLedger
from core.grounding import GroundingEngine
from core.failures import MissingDataError


def test_grounding_extracts_and_records(tmp_path: Path):
    ledger = FactLedger(base_dir=tmp_path)
    engine = GroundingEngine(ledger=ledger)
    facts = engine.extract(
        project_id="proj-1",
        backlog_item_id="item-1",
        rows=[{"text": "do work", "estimated_minutes": 30, "id": "r1"}],
    )
    assert len(facts.facts) == 2
    entries = ledger.load_entries("proj-1")
    assert entries[0]["backlog_item_id"] == "item-1"
    assert entries[0]["facts"][0]["provenance"]["row_id"] == "r1"


def test_grounding_requires_rows(tmp_path: Path):
    engine = GroundingEngine(ledger=FactLedger(base_dir=tmp_path))
    with pytest.raises(MissingDataError):
        engine.extract(project_id="p", backlog_item_id="b", rows=[])
