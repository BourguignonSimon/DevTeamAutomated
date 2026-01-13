| Requirement | Status (PASS/FAIL) | Evidence pointer |
| --- | --- | --- |
| R1. docker compose up starts everything and at least one consumer reads a Redis Stream | FAIL | [R1 Evidence](#r1-docker-compose-boot--consumer-read) |
| R2. Every event validated against JSON Schema (Draft 2020-12) before processing | PASS | [R2 Evidence](#r2-contract-validation-before-processing) |
| R3. Invalid events go to DLQ and do not block system | PASS | [R3 Evidence](#r3-dlq-routing-for-invalid-events) |
| R4. Orchestrator backlog generation, Redis state, state machine enforced | PASS | [R4 Evidence](#r4-orchestrator-backlog--state-machine) |
| R5. Dispatch with per-backlog_item_id lock | PASS | [R5 Evidence](#r5-dispatch-locking) |
| R6. Idempotence per consumer group | PASS | [R6 Evidence](#r6-idempotence) |
| R7. Retry + pending reclaim + deterministic DLQ | PASS | [R7 Evidence](#r7-retry-and-pending-reclaim) |
| R8. Clarification loop resumes after single answer | PASS | [R8 Evidence](#r8-clarification-loop) |
| R9. LLM Gateway with schema validation + fallback + human approval | PASS | [R9 Evidence](#r9-llm-gateway--human-approval) |
| R10. Observability with correlation/causation IDs within 10s | FAIL | [R10 Evidence](#r10-observability) |
| R11. Demo scripts for happy path + failure/DLQ + clarification | PASS | [R11 Evidence](#r11-demo-scripts) |
| R12. Output artifacts stored/linked to backlog items | PASS | [R12 Evidence](#r12-output-artifacts) |

# Architecture Map / Inventory

## Services
Defined in `docker-compose.yml`:
- `redis` (Redis 7, exposed 6380)
- `orchestrator` (consumes `audit:events`, group `orchestrator`)
- `validator` (schema validation consumer group `validators`)
- `worker` (generic consumer group `workers`)
- Specialized workers: `time_waste_worker`, `cost_worker`, `friction_worker`, `scenario_worker`, `requirements_manager_worker`, `dev_worker`, `test_worker`
- `order_intake_agent` (HTTP intake + LLM gateway)
- `llm_gateway` (provider-agnostic gateway)

## Streams / DLQ
- Default stream: `audit:events` (`core/config.py` + `docker-compose.yml`)
- DLQ stream: `audit:dlq`

## Consumer groups + consumers (from compose)
- Orchestrator: group `orchestrator`, consumer `orchestrator-1`
- Validator: group `validators`, consumer `validator-1`
- Worker: group `workers`, consumer `worker-1`
- Specialized groups: `time_waste_workers`, `cost_workers`, `friction_workers`, `scenario_workers`, `requirements_manager_workers`, `dev_workers`, `test_workers`
- Order intake: group `order_intake`, consumer `order-intake-1`

## Schemas
- Event envelope: `schemas/envelope/event_envelope.v1.schema.json`
- Payload schemas: `schemas/events/*.json`
- Shared object schemas: `schemas/objects/*.json`

# Verification Evidence

## R1. docker compose boot + consumer read
Command:
```
$ docker compose version
bash: command not found: docker
```
Status: **FAIL** in this environment because Docker CLI is unavailable; compose-based runtime verification could not be executed here.

## R2. Contract validation before processing
Evidence:
- JSON Schema Draft 2020-12 validator is used in `core/schema_validate.py`.
- Stream processor validates envelope and payload before handler execution in `core/stream_runtime.py`.
- Automated tests: `pytest -q tests/verification` (see output below).

Output excerpt:
```
$ pytest -q tests/verification
.......                                                                  [100%]
7 passed in 0.18s
```

## R3. DLQ routing for invalid events
Evidence:
- `ReliableStreamProcessor` sends invalid envelopes/payloads to DLQ and ACKs the message.
- Test coverage in `tests/verification/test_verification_pack.py::test_dlq_routing_does_not_block_valid_events`.

Output excerpt:
```
$ pytest -q tests/verification
.......                                                                  [100%]
7 passed in 0.18s
```

## R4. Orchestrator backlog + state machine
Evidence:
- Backlog template and dispatch logic in `services/orchestrator/main.py`.
- Redis-backed backlog store in `core/backlog_store.py` (JSON document storage in Redis strings).
- State machine rules in `core/state_machine.py`.
- Clarification test verifies backlog items transition from BLOCKED to READY/IN_PROGRESS: `tests/verification/test_verification_pack.py::test_clarification_loop_with_orchestrator`.

## R5. Dispatch locking
Evidence:
- Per-backlog lock acquisition using Redis `SET NX PX` in `core/locks.py`.
- Locks enforced in worker handlers (`services/*_worker/main.py` and `services/worker/main.py`) using `settings.key_prefix:lock:backlog:{backlog_item_id}`.

## R6. Idempotence
Evidence:
- Idempotence guard in `core/idempotence.py` and `core/stream_runtime.py`.
- Test coverage in `tests/verification/test_verification_pack.py::test_idempotence_per_consumer_group`.

## R7. Retry and pending reclaim
Evidence:
- Pending reclaim via `XAUTOCLAIM` implemented in `core/redis_streams.read_group` and `core/stream_runtime.ReliableStreamProcessor.consume_once`.
- Retry/poison handling tested in `tests/verification/test_verification_pack.py::test_retry_pending_reclaim_and_dlq`.

## R8. Clarification loop
Evidence:
- Orchestrator emits `QUESTION.CREATED` and `CLARIFICATION.NEEDED` then unblocks on `USER.ANSWER_SUBMITTED` in `services/orchestrator/main.py`.
- `USER.ANSWER_SUBMITTED` schema added in `schemas/events/user.answer_submitted.v1.schema.json`.
- Test coverage: `tests/verification/test_verification_pack.py::test_clarification_loop_with_orchestrator`.

## R9. LLM Gateway + human approval
Evidence:
- Gateway routes provider responses and validates output schema in `services/llm_gateway/main.py`.
- Provider fallback/retry loop implemented in `services/llm_gateway/main.py`.
- Human approval gate enforced by orchestrator events in `tests/test_human_approval_gate.py`.

## R10. Observability
Command:
```
$ docker compose version
bash: command not found: docker
```
Status: **FAIL** in this environment because runtime logs could not be inspected. Code-level logging + trace scaffolding exists in `core/trace.py` and service logs, but end-to-end log evidence was not captured here.

## R11. Demo scripts
Evidence:
- `demo/demo_happy_path.sh`
- `demo/demo_failure_retry_dlq.sh`
- `demo/demo_clarification.sh`
- `Makefile` targets: `demo`, `demo-happy`, `demo-failure`, `demo-clarification`

## R12. Output artifacts
Evidence:
- Deliverables include `project_id` + `backlog_item_id` in payload schema `schemas/events/deliverable.published.v1.schema.json`.
- Order intake agent exports artifacts to `storage/exports` and publishes `DELIVERABLE.PUBLISHED`/`ORDER.EXPORT_READY` events (`services/order_intake_agent/processor.py`).
