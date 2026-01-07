#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
import json, uuid
import redis
from core.event_utils import envelope
r = redis.Redis(host="localhost", port=6380)
project_id = str(uuid.uuid4())
env = envelope(
    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
    payload={"project_id": project_id, "request_text": "full audit with rows"},
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print("seeded project", project_id)
PY
