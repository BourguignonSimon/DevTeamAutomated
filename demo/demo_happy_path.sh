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

echo "==> Starting happy path demo"
$COMPOSE up -d --build redis orchestrator validator time_waste_worker >/dev/null

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
project_id = str(uuid.uuid4())
backlog_item_id = str(uuid.uuid4())
env = envelope(
    event_type="WORK.ITEM_DISPATCHED",
    payload={
        "project_id": project_id,
        "backlog_item_id": backlog_item_id,
        "item_type": "AGENT_TASK",
        "agent_target": "time_waste_worker",
        "work_context": {
            "rows": [
                {"category": "ops", "estimated_minutes": 30, "text": "ticket triage"},
                {"category": "meetings", "estimated_minutes": 45, "text": "status review"},
            ],
            "hourly_rate": 120,
            "period": {"type": "monthly", "working_days": 20},
        },
    },
    source="demo",
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print(f"SEEDED project_id={project_id} backlog_item_id={backlog_item_id} event_id={env['event_id']}")
PY

$COMPOSE exec -T orchestrator python - <<'PY'
import json
import time
import redis

r = redis.Redis(host="redis", port=6379, decode_responses=True)
deadline = time.time() + 10
found = None
while time.time() < deadline:
    events = r.xrange("audit:events", min="-", max="+")
    for _, fields in events:
        env = json.loads(fields.get("event", "{}"))
        if env.get("event_type") == "DELIVERABLE.PUBLISHED":
            found = env
            break
    if found:
        break
    time.sleep(0.5)

if not found:
    raise SystemExit("FAIL: deliverable not published")

payload = found.get("payload", {})
deliverable = payload.get("deliverable", {})
print(
    "PASS: deliverable published",
    f"backlog_item_id={payload.get('backlog_item_id')}",
    f"type={deliverable.get('type')}",
)
PY

pass "happy path complete"
