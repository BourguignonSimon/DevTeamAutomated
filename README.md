# Agentic Worklfow 

Agentic Worklfow is a general-purpose event-driven workflow toolkit. It ships with an audit-themed default configuration, but every key namespace and stream name can be overridden so the same package works for any workflow domain. It will be used for any automation/process simplification using agentic AI fully organized.

## About

**Description:** Workflow événementiel et agents IA pour orchestrer des processus, valider des événements, et produire des livrables automatisés via Redis Streams.  
**Topics:** `python`, `ai-agents`, `redis-streams`, `orchestrator`, `automation`  
**Website/Demo:** [`docs/TOOL_USAGE.md`](docs/TOOL_USAGE.md) (guide pas-à-pas avec exécution locale et démos HTTP)

This package includes:
- strict JSON contracts (EventEnvelope + payload schemas) and a generic validator consumer.
- Orchestrator (state machine, backlog generation, dispatch, DoD enforcement).
- AI agent teams design for audit operations (see `docs/EPIC5_AI_AGENT_TEAMS.md`).

For a step-by-step usage walkthrough (Docker Compose, Python entrypoints, HTTP gateway, and order intake flows), see
`docs/TOOL_USAGE.md`.

## Quickstart (runtime stack)

Bring up Redis, orchestrator, schema validator, and worker agents with Docker Compose:

```bash
docker compose up --build
```

### Use a custom namespace

By default, stream names and Redis keys use the `audit` namespace. To reuse the toolkit for other workflows, override the namespace or specific prefixes:

```bash
export NAMESPACE=workflow
# Optional granular overrides:
# export STREAM_NAME=workflow:events
# export DLQ_STREAM=workflow:dlq
# export KEY_PREFIX=workflow
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

Alternatively, you can drive the same flow over HTTP for quick demos:

```bash
# in one terminal
python -m demo.http_gateway

# in another terminal
curl -X POST http://localhost:8080/initial-request \
  -H 'Content-Type: application/json' \
  -d '{"request_text": "full audit via curl"}'
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

### Order intake demo (RUN mode)

Run Docker Compose and use the order intake gateway (FastAPI-compatible stub) exposed on port 8080:

```bash
docker compose up --build order_intake_agent redis
```

Submit an email-style order with attachments:

```bash
curl -X POST http://localhost:8080/orders/inbox \
  -F from_email='user@example.com' \
  -F subject='New order' \
  -F delivery_address='123 Example St' \
  -F delivery_date='2024-01-02' \
  -F files=@./sample_order.xlsx
```

List pending validations (orders that raised missing fields or anomalies):

```bash
curl http://localhost:8080/orders/pending-validation
```

Submit corrections/validation:

```bash
curl -X POST http://localhost:8080/orders/<order_id>/validate \
  -H 'Content-Type: application/json' \
  -d '{"delivery": {"address": "123 Example St", "date": "2024-01-02"}}'
```

### LLM gateway + human approval demo (RUN mode)

The Docker Compose stack now includes a provider-agnostic LLM gateway (`llm_gateway`) used by the order intake agent. The order agent never calls providers directly; it always targets the gateway at `LLM_GATEWAY_URL`. See `docs/AI_AGENT_SOLUTION.md` for the full AI agent LLM mechanism and safety rails.

1. Start the stack (Redis, order intake agent, and gateway):

   ```bash
   docker compose up --build redis llm_gateway order_intake_agent
   ```

2. Post an order inbox request with an Excel attachment as above. The gateway will generate a draft, but export is held for human approval.

3. Check pending validation items:

   ```bash
   curl http://localhost:8080/orders/pending-validation
   ```

4. Approve the order (this is mandatory; no export occurs before validation):

   ```bash
   curl -X POST http://localhost:8080/orders/<order_id>/validate -H 'Content-Type: application/json' -d '{}'
   ```

5. After validation, the agent exports a CSV to the shared `storage/exports` directory (mounted from the host). Published events `ORDER.EXPORT_READY` and `DELIVERABLE.PUBLISHED` will now appear on the `audit:events` stream.

Artifacts (uploaded attachments and generated CSV exports) are stored under `./storage` and indexed in Redis with a TTL.

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

Reliability of the Redis Streams runtime (schema validation, retries, DLQ, and idempotence) is covered by dedicated unit tests:

```bash
pytest -q tests/test_reliable_runtime.py
```

Integration tests that exercise the real Compose stack are tagged `integration` and will be skipped automatically unless Docker is available.
