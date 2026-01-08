#!/usr/bin/env bash
set -euo pipefail

COMPOSE=${COMPOSE:-"docker compose"}

fail() {
  echo "FAIL: $1"
  exit 1
}

pass() {
  echo "PASS: $1"
}

echo "==> Starting failure + DLQ demo"
$COMPOSE up -d --build redis orchestrator validator >/dev/null

ready=0
for _ in {1..30}; do
  if $COMPOSE exec -T redis redis-cli ping >/dev/null 2>&1; then
    pass "redis reachable"
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  fail "redis not reachable"
fi

$COMPOSE exec -T orchestrator python - <<'PY'
import json
import uuid
import redis
from core.event_utils import envelope

r = redis.Redis(host="redis", port=6379, decode_responses=True)
env = envelope(
    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
    payload={"project_id": str(uuid.uuid4())},
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print(f"SEEDED invalid event_id={env['event_id']}")
PY

$COMPOSE exec -T orchestrator python - <<'PY'
import json
import time
import redis

r = redis.Redis(host="redis", port=6379, decode_responses=True)
deadline = time.time() + 10
found = None
while time.time() < deadline:
    entries = r.xrange("audit:dlq", min="-", max="+")
    if entries:
        _mid, fields = entries[-1]
        found = json.loads(fields.get("dlq", "{}"))
        break
    time.sleep(0.5)

if not found:
    raise SystemExit("FAIL: DLQ entry not found")

print("PASS: DLQ entry recorded", f"reason={found.get('reason')}")
PY

pass "failure + DLQ demo complete"
