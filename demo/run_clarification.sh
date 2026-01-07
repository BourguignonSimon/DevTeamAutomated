#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import json, uuid
import redis
from core.event_utils import envelope
from core.grounding import GroundingEngine
from core.fact_ledger import FactLedger
engine = GroundingEngine(ledger=FactLedger())
try:
    engine.extract(project_id="demo", backlog_item_id="item", rows=[])
except Exception as e:
    print("clarification required:", e)
PY
