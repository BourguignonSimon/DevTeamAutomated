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

echo "==> Starting clarification demo"
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
import time
import uuid
import redis
from core.event_utils import envelope
from core.backlog_store import BacklogStore
from core.question_store import QuestionStore

r = redis.Redis(host="redis", port=6379, decode_responses=True)
project_id = str(uuid.uuid4())
correlation_id = str(uuid.uuid4())

env = envelope(
    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
    payload={"project_id": project_id, "request_text": "kpi"},
    source="demo",
    correlation_id=correlation_id,
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})

deadline = time.time() + 10
question_id = None
while time.time() < deadline:
    entries = r.xrange("audit:events", min="-", max="+")
    types = {json.loads(f.get("event", "{}")).get("event_type") for _, f in entries}
    if "QUESTION.CREATED" in types and "CLARIFICATION.NEEDED" in types:
        qs = QuestionStore(r)
        open_qs = qs.list_open(project_id)
        if open_qs:
            question_id = open_qs[0]
            break
    time.sleep(0.5)

if not question_id:
    raise SystemExit("FAIL: clarification events not found")

print("PASS: clarification emitted", f"question_id={question_id}")

answer_env = envelope(
    event_type="USER.ANSWER_SUBMITTED",
    payload={"project_id": project_id, "question_id": question_id, "answer": "Answer provided"},
    source="demo",
    correlation_id=correlation_id,
    causation_id=env["event_id"],
)
r.xadd("audit:events", {"event": json.dumps(answer_env)})

store = BacklogStore(r)
deadline = time.time() + 10
unblocked = False
while time.time() < deadline:
    entries = r.xrange("audit:events", min="-", max="+")
    types = {json.loads(f.get("event", "{}")).get("event_type") for _, f in entries}
    if "BACKLOG.ITEM_UNBLOCKED" in types:
        unblocked = True
        break
    time.sleep(0.5)

if not unblocked:
    raise SystemExit("FAIL: backlog item not unblocked")

print("PASS: backlog item unblocked")
PY

pass "clarification demo complete"
