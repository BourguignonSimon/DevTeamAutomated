# Audit Flash

This package includes:
- **EPIC 1**: strict JSON contracts (EventEnvelope + payload schemas) and a generic validator consumer.
- **EPIC 2**: Orchestrator (state machine, backlog generation, dispatch, DoD enforcement).

## Quickstart (runtime stack)

Bring up Redis, orchestrator, schema validator, and worker with Docker Compose:

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
2. Worker consumes dispatches and emits `WORK.ITEM_STARTED` + `WORK.ITEM_COMPLETED`.
3. Validator sends any contract violations to `audit:dlq` without blocking other consumers.

## Tests

```bash
make test
```

Integration tests that exercise the real Compose stack are tagged `integration` and will be skipped automatically unless Docker is available.
