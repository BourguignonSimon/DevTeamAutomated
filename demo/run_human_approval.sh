#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import json, uuid
import redis
from core.event_utils import envelope
r = redis.Redis(host="localhost", port=6380)
project_id = str(uuid.uuid4())
backlog_id = str(uuid.uuid4())
req = envelope(
    event_type="HUMAN.APPROVAL_REQUESTED",
    payload={"project_id": project_id, "backlog_item_id": backlog_id, "reason": "manual review"},
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
sub = envelope(
    event_type="HUMAN.APPROVAL_SUBMITTED",
    payload={"project_id": project_id, "backlog_item_id": backlog_id, "approved": True},
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=req["event_id"],
)
r.xadd("audit:events", {"event": json.dumps(req)})
r.xadd("audit:events", {"event": json.dumps(sub)})
print("approval simulated for", backlog_id)
PY
