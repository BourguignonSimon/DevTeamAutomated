# Audit Flash

This package includes:
- **EPIC 1**: strict JSON contracts (EventEnvelope + payload schemas) and a generic validator consumer.
- **EPIC 2**: Orchestrator (state machine, backlog generation, dispatch, DoD enforcement).
- **EPIC 5**: AI agent teams design for audit operations (see `docs/EPIC5_AI_AGENT_TEAMS.md`).

## Quickstart (runtime stack)

Bring up Redis, orchestrator, schema validator, and the four EPIC5 worker agents with Docker Compose:

```bash
docker compose up --build
```

Redis is exposed on **localhost:6380**. Publish an intake event to trigger the flow:

```bash
python - <<'PY'
import json, uuid, redis
from core.event_utils import envelope

r = redis.Redis(host="localhost", port=6380)
env = envelope(
    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
    source="demo",
    payload={"project_id": str(uuid.uuid4()), "request_text": "full audit"},
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print("seeded", env["event_id"])
PY
```

### What to observe

1. Orchestrator generates a backlog and dispatches `WORK.ITEM_DISPATCHED`.
2. Worker agents (time waste, cost, friction, scenario) consume dispatches targeted to them and emit `WORK.ITEM_STARTED`, `DELIVERABLE.PUBLISHED`, and `WORK.ITEM_COMPLETED`.
3. Validator sends any contract violations to `audit:dlq` without blocking other consumers.

### Manual demo without orchestrator

You can send a ready-to-run dispatch directly to the stream to watch the agents produce deliverables end-to-end:

```bash
python - <<'PY'
import json, uuid, redis
from core.event_utils import envelope

r = redis.Redis(host="localhost", port=6380)
work_context = {
    "rows": [
        {"category": "ops", "estimated_minutes": 30, "text": "ticket triage"},
        {"category": "meetings", "estimated_minutes": 45, "text": "status review"},
    ],
    "hourly_rate": 120,
    "period": {"type": "monthly", "working_days": 20},
}
env = envelope(
    event_type="WORK.ITEM_DISPATCHED",
    source="demo",
    payload={
        "project_id": str(uuid.uuid4()),
        "backlog_item_id": str(uuid.uuid4()),
        "item_type": "AGENT_TASK",
        "agent_target": "time_waste_worker",
        "work_context": work_context,
    },
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print("seeded dispatch", env["event_id"])
PY
```

### Inspecting streams

- Recent deliverables: `redis-cli -p 6380 XRANGE audit:events - + COUNT 20 | grep DELIVERABLE`.
- DLQ entries: `redis-cli -p 6380 XRANGE audit:dlq - + COUNT 5`.

### Resetting consumer groups

To delete and recreate a consumer group during local testing:

```bash
redis-cli -p 6380 XGROUP DESTROY audit:events time_waste_workers
redis-cli -p 6380 XGROUP CREATE audit:events time_waste_workers 0-0 MKSTREAM
```

## Tests

```bash
make test
```

Integration tests that exercise the real Compose stack are tagged `integration` and will be skipped automatically unless Docker is available.
