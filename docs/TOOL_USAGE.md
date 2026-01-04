# Audit Flash tool usage guide

This guide explains how to run the Audit Flash stack locally and how to use the tooling for event-stream and HTTP-based demos.

## Prerequisites
- **Python 3.11+** (for running services directly)
- **Docker** and **Docker Compose** (recommended for the full stack)
- **Redis** is provided in Docker Compose; no local install is required when using Compose.

## Option A: Run everything with Docker Compose (recommended)
1. Build and start the core services, Redis, and demo agents:
   ```bash
docker compose up --build
   ```
2. After the containers are healthy, publish an intake event to trigger the flow:
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
3. Observe recent deliverables and DLQ activity:
   ```bash
redis-cli -p 6380 XRANGE audit:events - + COUNT 20 | grep DELIVERABLE
redis-cli -p 6380 XRANGE audit:dlq - + COUNT 5
   ```

## Option B: Run services directly with Python
If you prefer not to use Docker, install dependencies and start the services manually:

1. Install Python dependencies:
   ```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
   ```
2. Start Redis (local install) or point the `REDIS_HOST`/`REDIS_PORT` env vars at an accessible instance.
3. Run the orchestrator, worker, and validator services in separate terminals:
   ```bash
python -m services.orchestrator.main
python -m services.worker.main
python -m services.stream_consumer.main
python -m services.time_waste_worker.main
python -m services.cost_worker.main
python -m services.friction_worker.main
python -m services.scenario_worker.main
   ```
4. Seed intake or dispatch events using the same snippets from the Docker Compose section.

## HTTP gateway demo
For a quick interactive demo over HTTP instead of direct Redis commands:

1. Start the gateway and dependencies:
   ```bash
# terminal 1
python -m demo.http_gateway
   ```
2. Submit a request through the HTTP endpoint (with the services running via Compose or Python):
   ```bash
# terminal 2
curl -X POST http://localhost:8080/initial-request \
  -H 'Content-Type: application/json' \
  -d '{"request_text": "full audit via curl"}'
   ```

## Order intake workflow (RUN mode)
The stack includes an order intake agent that uses the LLM gateway. To exercise it:

1. Start only the required services:
   ```bash
docker compose up --build redis llm_gateway order_intake_agent
   ```
2. Submit an order inbox request with an attachment:
   ```bash
curl -X POST http://localhost:8080/orders/inbox \
  -F from_email='user@example.com' \
  -F subject='New order' \
  -F delivery_address='123 Example St' \
  -F delivery_date='2024-01-02' \
  -F files=@./sample_order.xlsx
   ```
3. Review pending validations and approve when ready:
   ```bash
curl http://localhost:8080/orders/pending-validation
curl -X POST http://localhost:8080/orders/<order_id>/validate \
  -H 'Content-Type: application/json' \
  -d '{}'
   ```
4. After approval, exported CSVs appear under `./storage/exports`, and corresponding events (`ORDER.EXPORT_READY`, `DELIVERABLE.PUBLISHED`) show up on `audit:events`.

## Resetting consumer groups
During local testing, you might want to recreate consumer groups:
```bash
redis-cli -p 6380 XGROUP DESTROY audit:events time_waste_workers
redis-cli -p 6380 XGROUP CREATE audit:events time_waste_workers 0-0 MKSTREAM
```

## Running tests
Smoke and reliability tests can be run locally:
```bash
make test
# or
pytest -q tests/test_reliable_runtime.py
```

## Troubleshooting tips
- Ensure ports `6380` (Redis) and `8080` (HTTP gateway) are free before starting services.
- If you change environment variables in `core/config.py`, restart services to apply the new settings.
- Use `docker compose logs -f <service>` to monitor individual containers when running with Docker.
