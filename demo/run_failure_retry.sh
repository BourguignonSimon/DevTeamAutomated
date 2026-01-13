#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import json, uuid
import redis
from core.event_utils import envelope
r = redis.Redis(host="localhost", port=6380)
project_id = str(uuid.uuid4())
backlog_id = str(uuid.uuid4())
completed = envelope(
    event_type="WORK.ITEM_COMPLETED",
    payload={"project_id": project_id, "backlog_item_id": backlog_id, "evidence": {}},
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(completed)})
print("submitted incomplete completion", backlog_id)
PY
