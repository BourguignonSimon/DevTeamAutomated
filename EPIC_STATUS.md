# Epic implementation review

This repository already passes the bundled tests, but the test harness uses an in-memory Redis stub (`tests/conftest.py`) instead of the real services. The runtime services defined under `services/` therefore still need work to satisfy the four epics in real deployments.

## EPIC 0 – Foundations & Run Environment
**Observed:** `docker-compose.yml` wires Redis, the orchestrator image, and a test runner, but no container runs the contract-validation consumer or any worker that reads dispatched backlog items.

**Remaining actions:**
- Add the `stream_consumer` service (or equivalent) to Compose so envelope/payload validation happens in the deployed stack, not just in unit tests.
- Provide an actual worker/dispatcher entrypoint (or remove/replace `_dispatch_ready_tasks`) so emitted `WORK.ITEM_DISPATCHED` events can be consumed downstream.

## EPIC 1 – Contracts & Schemas
**Observed:** Schema loading/validation code exists, and the in-memory test stub enforces minimal envelope requirements, but the production orchestrator calls `publish_dlq` with the wrong signature and never runs because Compose does not start a validating consumer.

**Remaining actions:**
- Align `services/orchestrator/main.py` with `core.dlq.publish_dlq`’s signature so contract violations can be pushed to the DLQ in production.
- Wire the contract-validation consumer into the runtime stack (see EPIC 0) so every event is validated against the JSON Schemas before consumption.

## EPIC 2 – Orchestrator
**Observed:** The orchestrator module includes backlog creation and dispatch helpers, but several dependencies are missing or misaligned:
- `_dispatch_ready_tasks` is unused, calls an undefined `_now_iso()`, and depends on a `list_project_ids` helper that `BacklogStore` does not provide.
- The state machine enumerates no `DISPATCHED` status even though dispatch sets that value.

**Remaining actions:**
- Decide whether dispatch should set `READY`→`IN_PROGRESS` or introduce a `DISPATCHED` status and update `BacklogStatus` + allowed transitions accordingly.
- Implement a project index (`BacklogStore.list_project_ids()` or similar) and remove the undefined `_now_iso()` reference in `_dispatch_ready_tasks`.
- Confirm how backlog items should be hierarchized (epic/feature/task) and extend `BacklogStore`/templates accordingly.

## EPIC 3 – Clarification Loop
**Observed:** The orchestrator tries to create and close questions, but `QuestionStore` only exposes `put_question`, `get_question`, `set_answer`, and `list_*`; `create_question`/`close_question` do not exist. That would crash the runtime loop when a clarification is needed.

**Remaining actions:**
- Add `create_question`/`close_question` (or refactor the orchestrator to use the existing methods) so questions can be persisted and closed safely.
- Define the ambiguity-detection rules more precisely; current logic only checks request length or the presence of "kpi" without a question mark.

## Clarification requested
Should the production orchestrator be the single entrypoint for backlog generation and clarification handling, or should these responsibilities remain inside a separate consumer/worker like the in-memory stub used in tests? Your answer will drive whether we harden `services/orchestrator/main.py` or split the duties across services.
