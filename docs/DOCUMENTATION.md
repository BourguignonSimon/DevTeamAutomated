# Audit Flash Package Documentation

This document provides an end-to-end view of the Audit Flash codebase, spanning module layout, public classes and functions, and detailed behavioral notes for each component. It is organized in three layers:

1. **High-level view** of the repository structure and responsibilities.
2. **Function and class catalog** with brief descriptions grouped by module.
3. **Detailed module reference** describing data flow, parameters, return values, and domain rules.

## 1. High-level view

```
repo root
├── README.md                 # Quickstart and runtime overview
├── core/                     # Domain and infrastructure primitives
│   ├── agent_workers.py      # Shared compute helpers used by EPIC5 worker agents
│   ├── backlog_store.py      # Redis-backed backlog persistence helpers
│   ├── config.py             # Centralized runtime settings
│   ├── dlq.py                # Dead-letter publishing helpers
│   ├── event_utils.py        # Event envelope helpers
│   ├── idempotence.py        # Idempotent event tracking
│   ├── ingestion.py          # Task ingestion and normalization utilities
│   ├── locks.py              # Lightweight Redis locks
│   ├── logging.py            # Logging configuration helper
│   ├── question_store.py     # Redis-backed clarification question storage
│   ├── redis_streams.py      # Redis Streams client helpers
│   ├── schema_registry.py    # Schema discovery and loading
│   ├── schema_validate.py    # JSON schema validation helpers
│   └── state_machine.py      # Backlog state machine rules
├── services/                 # Executable services built on the core
│   ├── orchestrator/         # Generates and dispatches backlog; handles clarifications
│   │   └── main.py
│   ├── worker/               # Processes dispatched backlog items
│   │   └── main.py
│   ├── stream_consumer/      # Minimal validation-only consumer
│   │   └── main.py
│   ├── time_waste_worker/    # EPIC5 worker emitting time-waste analysis deliverables
│   ├── cost_worker/          # EPIC5 worker estimating hourly/monthly/annual costs
│   ├── friction_worker/      # EPIC5 worker detecting recurring tasks/friction
│   └── scenario_worker/      # EPIC5 worker projecting avoidable savings scenarios
├── demo/                     # Interactive helpers for seeding projects and answers
├── agent_manager.py          # Phase/timeout orchestrator for agent workflows
├── schemas/                  # JSON schema contracts for envelopes, events, and objects
└── tests/                    # Regression coverage and integration smoke tests
```

## 2. Function and class catalog

### `core.backlog_store`
- **BacklogStore**: Redis-backed CRUD and indexing for backlog items.
  - `_key`, `_index`, `_status_index`, `_projects_index`: Key builders.
  - `_decode`: Decode Redis bytes to string.
  - `put_item`: Upsert item and maintain indexes.
  - `set_status`: Update item status with indexing.
  - `get_item`: Fetch single backlog item.
  - `list_item_ids`, `list_item_ids_by_status`: Sorted ID listings.
  - `iter_items`, `iter_items_by_status`: Generators yielding full items.
  - `list_project_ids`: Enumerate known projects.

### `core.config`
- **Settings**: Frozen dataclass with environment-driven configuration (Redis, timeouts, stream names, locks, logging).

### `core.dlq`
- `_try_parse_event`: Best-effort decode of serialized event for DLQ context.
- `publish_dlq`: Build and publish a DLQ record with metadata and original fields.

### `core.event_utils`
- `now_iso`: UTC timestamp formatter.
- `new_event_id`: UUID generator for events.
- `envelope`: Construct EPIC-1 compliant event envelope with correlation/causation IDs.

### `core.idempotence`
- `mark_if_new`: Redis SETNX helper to mark processed event IDs with TTL.

### `core.ingestion`
- **DetectedColumns**: Dataclass capturing chosen text/category/duration headers.
- `_normalize_header`: Lowercase + punctuation stripping for header comparison.
- `detect_useful_columns`: Heuristic detection of task text/category/duration columns.
- `_clean_text`: Whitespace normalization and safe string conversion.
- `infer_category`: Derive category from provided value or text keywords.
- `_parse_duration_minutes`: Parse numeric durations with unit handling to minutes.
- `estimate_duration_minutes`: Predict duration when parsing fails using task length heuristics.
- `normalize_rows`: Transform raw rows into normalized backlog-ready entries.
- `load_csv`: CSV ingestion into list-of-dicts rows.
- `load_excel`: Excel ingestion using `openpyxl` (sheet selection optional).

### `core.locks`
- `acquire_lock`: Acquire Redis-based lock with TTL using SET NX EX.
- `release_lock`: Release lock by key deletion.

### `core.logging`
- `setup_logging`: Configure logging level and format.

### `core.question_store`
- **QuestionStore**: Redis-backed clarification question persistence.
  - `_qkey`, `_index`, `_open`, `_answer_key`: Key builders.
  - `_decode`: Decode Redis bytes to string.
  - `create_question`: Create and store new question object.
  - `put_question`: Upsert question with indexes.
  - `get_question`: Retrieve question by ID.
  - `list_open`, `list_all`: Sorted listings of question IDs.
  - `set_answer`: Store normalized answer and close question.
  - `get_answer`: Retrieve stored answer.
  - `close_question`: Mark question as closed and remove from open set.

### `core.redis_streams`
- `build_redis_client`: Create Redis client with decoded responses.
- `ensure_consumer_group`: Create consumer group/stream if absent.
- `read_group`: Prefer new stream entries then reclaim stale pending messages.
- `ack`: Acknowledge processed message.

### `core.schema_registry`
- `_load_json`: Load JSON schema file from disk.
- `_resolve_base_dir`: Choose schema directory from provided path, env override, or repo default.
- **SchemaRegistry**: Dataclass bundling envelope/object/payload schemas.
- `load_registry`: Build registry by loading envelope, object, and event payload schemas; validates uniqueness.

### `core.schema_validate`
- **ValidationResult**: Dataclass for schema validation outcomes.
- `_validate`: Core JSON Schema validation helper returning `ValidationResult`.
- `validate_envelope`: Validate event envelope.
- `validate_payload`: Validate event payload by type with graceful missing-schema handling.

### `core.state_machine`
- **BacklogStatus**: Enum of backlog lifecycle states.
- `_ALLOWED`: Transition adjacency map.
- **TransitionResult**: Dataclass describing transition outcome.
- `is_allowed`: Check if a transition is permitted.
- `assert_transition`: Raise on illegal transitions; return result on success.

### `core.agent_workers`
- `normalize_text`: Lowercase, strip punctuation, and collapse whitespace to fingerprint task text.
- `compute_time_metrics`: Sum estimated minutes/hours and return per-category breakdown and shares.
- `compute_confidence`: Heuristic score incorporating hourly rate presence, row count, category diversity, and missing estimates.
- `compute_costs`: Convert total hours and hourly rate into monthly/annual costs.
- `compute_friction`: Detect recurring work by text fingerprint; returns cluster breakdown and avoidable percent estimate.
- `compute_scenario`: Combine friction and cost metrics into a recovered-hours savings projection.

### `services.orchestrator.main`
- `envelope`: Service-local envelope constructor mirroring test style.
- `_backlog_template`: Deterministic backlog seed for new projects.
- `_needs_clarification`: Detect ambiguous requests; return flag and reason text.
- `_apply_status_safe`: Attempt status transition with safe error handling.
- `_dlq`: Publish DLQ entry preserving original event metadata.
- `_now_iso`: UTC timestamp helper.
- `process_message`: Core orchestrator handler for intake and answers; manages DLQ and idempotence.
- `_dispatch_ready_tasks`: Emit `WORK.ITEM_DISPATCHED` and update statuses for READY items.
- `main`: Service entrypoint: setup, stream loop, and message dispatch.

### `services.stream_consumer.main`
- `process`: Validate envelope and payload for incoming events; raise on issues.
- `main`: Entry point wiring Redis stream consumption and DLQ on validation errors.

### `services.worker.main`
- `_handle_dispatch`: Validate dispatch payload, emit started/completed events, and update statuses.
- `_process_message`: Stream handler for dispatched work with DLQ on errors.
- `main`: Worker entry point for consuming dispatches.

### `services.time_waste_worker.main`
- `_emit_started`: Emit `WORK.ITEM_STARTED` for matching dispatches.
- `_emit_deliverable`: Publish `DELIVERABLE.PUBLISHED` with total minutes/hours breakdown and mark completion.
- `_emit_clarification`: Request missing `work_context.rows` inputs via `CLARIFICATION.NEEDED`.
- `_process_message`: Validate envelope/payload, enforce idempotence, route only `AGENT_TASK` dispatches targeting this agent, and drive started/deliverable events or clarification.
- `main`: Consume stream events with group/consumer settings and delegate to `_process_message`.

### `services.cost_worker.main`
- `_emit_started`: Emit `WORK.ITEM_STARTED` upon valid dispatch.
- `_emit_clarification`: Request missing `hourly_rate`/`rows` inputs.
- `_emit_results`: Produce cost analysis deliverable and completion evidence derived from time metrics and hourly rate.
- `_process_message`: Validate dispatch, gate on agent target, enforce idempotence, branch to clarification or result emission.
- `main`: Wire Redis consumption loop for the cost worker agent.

### `services.friction_worker.main`
- `_emit_started`: Emit started event for this agent.
- `_emit_results`: Compute friction clusters/avoidable work and publish deliverable plus completion evidence.
- `_emit_clarification`: Request `rows` when absent.
- `_process_message`: Validate dispatch, confirm agent target, enforce idempotence, and either clarify or emit started/results.
- `main`: Run stream consumption loop for friction analysis agent.

### `services.scenario_worker.main`
- `_emit_started`: Emit started event for dispatched tasks.
- `_emit_clarification`: Request missing `hourly_rate` or `rows` inputs.
- `_emit_results`: Combine time, friction, and cost metrics into a savings scenario deliverable and completion evidence.
- `_process_message`: Validate dispatch, confirm agent target, enforce idempotence, and branch between clarification and result publication.
- `main`: Stream loop wiring for the scenario agent.

### `agent_manager`
- **Phase**: Enum of agent workflow phases (analyse, architecture, code, review).
- **PhaseState**: Dataclass capturing phase progress metadata.
- **StateJournal**: Dual persistence (Redis + file) for last-known phase state.
  - `record`, `clear`, `last_known_state`: Manage persisted state entries.
- **AgentManager**: Executes phase handlers with timeouts, persistence, retry, and incident hooks.
  - `_timeout_for_phase`, `_execute_with_timeout`, `_persist_phase`, `_handle_failure`, `_run_phase`, `_run_review_with_retry`: Internal helpers.
  - `run_workflow`: Execute ordered phases with timeout enforcement and retry behavior.

### `demo` helpers
- `interactive_demo`: CLI menu for seeding intake events, dispatching manual work, simulating worker outputs, and inspecting DLQ/backlog keys.
- `seed_events`: One-shot script to seed a `PROJECT.INITIAL_REQUEST_RECEIVED` event for demos.
- `clarification_demo`: Interactive prompt to fetch open questions from Redis and emit `USER.ANSWER_SUBMITTED` events.

## 3. Detailed module reference

### `core.backlog_store`
Backlog items are persisted as JSON blobs in Redis and indexed by project and status to support efficient listing and filtering.

- **BacklogStore(r, prefix="audit")**: Accepts a Redis client and optional key prefix.
  - `_key(project_id, item_id)`, `_index(project_id)`, `_status_index(project_id, status)`, `_projects_index()`: Compose deterministic Redis keys for item storage and indexes.
  - `_decode(v)`: Normalize bytes/strings to string for Redis set members.
  - `put_item(item) -> None`: Upserts the item document, adds it to project and status indexes, and updates the project registry. If the status changes, the old status index entry is removed.
  - `set_status(project_id, item_id, new_status) -> None`: Loads the item, validates existence, updates status, and reindexes via `put_item`.
  - `get_item(project_id, item_id) -> dict | None`: Fetch and decode a stored item, returning `None` when absent.
  - `list_item_ids(project_id) -> List[str]`: Sorted set of all backlog IDs for a project.
  - `list_item_ids_by_status(project_id, status) -> List[str]`: Sorted IDs filtered by status.
  - `iter_items(project_id) -> Iterable[dict]`: Yield stored items in ID order.
  - `iter_items_by_status(project_id, status) -> Iterable[dict]`: Yield items matching a status.
  - `list_project_ids() -> List[str]`: Sorted project identifiers observed in the backlog store.

### `core.config`
Centralized settings via environment variables. Defaults target Docker Compose runtime (Redis host `redis`, stream names `audit:events`/`audit:dlq`, consumer settings, lock TTLs, and logging level).

- **Settings**: Frozen dataclass so instances are hashable and immutable after creation.

### `core.dlq`
Utilities for emitting dead-letter entries to Redis streams while preserving original event context.

- `_try_parse_event(original_fields) -> dict`: Attempts JSON decode of the `event` field; returns empty dict on failure or absence.
- `publish_dlq(r, dlq_stream, reason, original_fields, schema_id=None) -> str`: Builds a DLQ document containing timestamp, event metadata, reason, schema ID, decoded event when available, and raw fields; publishes via `XADD` and returns the new message ID.

### `core.event_utils`
Helpers for producing EPIC-1 compliant envelopes and time-safe identifiers.

- `now_iso() -> str`: Current UTC timestamp in RFC3339-like format (`YYYY-MM-DDTHH:MM:SSZ`).
- `new_event_id() -> str`: Wrapper around `uuid.uuid4()` returning string.
- `envelope(event_type, payload, source, event_version=1, correlation_id=None, causation_id=None, instance=None) -> dict`: Constructs the canonical envelope with correlation/causation IDs and source metadata. Correlation ID and instance default to generated values when omitted.

### `core.idempotence`
Prevent duplicate processing of events using Redis SETNX semantics.

- `mark_if_new(r, event_id, ttl_s=604800, prefix="audit:processed:event") -> bool`: Writes a namespaced key with TTL only if absent; returns `True` when the event is new, `False` if previously seen.

### `core.ingestion`
Transforms external tabular task definitions into normalized backlog-ready records.

- **DetectedColumns(text, category, duration)**: Captures the selected column headers for task text, category, and duration.
- `_normalize_header(header) -> str`: Lowercase, trim, and replace non-alphanumeric characters with spaces to simplify matching.
- `detect_useful_columns(headers) -> DetectedColumns`: Matches normalized headers against heuristics (task/title/description/etc.). Raises `ValueError` if no text-like column is found. Category/duration are optional.
- `_clean_text(value) -> str`: Converts any value to string, collapses whitespace, and trims; `None` yields empty string.
- `infer_category(raw_category, task_text) -> str`: Prioritize cleaned `raw_category`; otherwise map keywords in `task_text` to canonical categories with fallback `"uncategorized"`.
- `_parse_duration_minutes(value) -> int | None`: Parse numbers and optional units (minutes/hours/days). Returns `None` on invalid or non-positive input.
- `estimate_duration_minutes(raw_value, task_text) -> int`: Use parsed minutes when available; otherwise estimate based on word count (short → 30m, medium → 60m, long → 120m).
- `normalize_rows(rows) -> List[dict]`: Detects columns, cleans text, infers category and estimated duration, and preserves original row data under `source_row`.
- `load_csv(path) -> List[MutableMapping[str, object]]`: Read CSV using `csv.DictReader` with UTF-8 decoding.
- `load_excel(path, sheet_name=None) -> List[MutableMapping[str, object]]`: Read Excel via `openpyxl` in read-only mode; selects a named sheet or defaults to active; builds row dictionaries from header row and subsequent values.

### `core.locks`
Minimal lock helpers for coordinating distributed actions.

- `acquire_lock(r, key, ttl_s=120) -> bool`: Attempts to set a lock key with TTL using `SET NX EX`; returns success flag.
- `release_lock(r, key) -> None`: Deletes the lock key without safety checks.

### `core.logging`
Single entry point to configure logging format across services.

- `setup_logging(level="INFO") -> None`: Configures root logger level and format string.

### `core.question_store`
Manages clarification questions linked to backlog items while keeping the underlying object schema strict.

- **QuestionStore(r, prefix="audit")**: Accepts Redis client and key prefix.
  - `_qkey`, `_index`, `_open`, `_answer_key`: Construct Redis keys for storing questions, indexes, open set, and answers.
  - `_decode(v)`: Normalize Redis byte/string members.
  - `create_question(project_id, backlog_item_id, question_text, answer_type, status="OPEN", correlation_id=None) -> dict`: Generates UUID, constructs question object, stores it, and returns it.
  - `put_question(q) -> None`: Upserts question, adds to indexes and open set.
  - `get_question(project_id, question_id) -> dict | None`: Retrieve stored question JSON.
  - `list_open(project_id) -> List[str]`: Sorted IDs of open questions.
  - `list_all(project_id) -> List[str]`: Sorted IDs of all questions for the project.
  - `set_answer(project_id, question_id, normalized_answer) -> None`: Stores JSON-encoded answer and removes question from open set.
  - `get_answer(question_id) -> Any | None`: Retrieves stored answer, decoding JSON.
  - `close_question(project_id, question_id) -> None`: Marks status `CLOSED` if needed and removes from open set.

### `core.redis_streams`
Encapsulates Redis Stream consumption patterns with safe group creation and pending-claim logic.

- `build_redis_client(host, port, db=0) -> redis.Redis`: Returns a client with `decode_responses=True` for string values.
- `ensure_consumer_group(r, stream, group) -> None`: Creates consumer group and stream if absent; ignores `BUSYGROUP` errors when the group exists.
- `read_group(r, stream, group, consumer, block_ms=2000, count=10, reclaim_min_idle_ms=None, reclaim_count=50) -> List[(id, fields)]`: Reads new messages first; if none and reclaim parameters provided, attempts `XAUTOCLAIM` to recover stale pending messages.
- `ack(r, stream, group, msg_id) -> None`: Acknowledge processed messages.

### `core.schema_registry`
Loads JSON schema contracts from a configurable base directory with fallbacks for local and containerized runs.

- `_load_json(path) -> dict`: Read JSON file with UTF-8 encoding.
- `_resolve_base_dir(base_dir) -> str`: Returns first existing directory among the provided path, `SCHEMA_BASE_DIR` env override, or repository `schemas/`; raises `FileNotFoundError` if none exist.
- **SchemaRegistry(envelope, objects, payloads)**: Dataclass bundling loaded schemas.
- `load_registry(base_dir) -> SchemaRegistry`: Loads envelope schema, object schemas (if any), and event payload schemas keyed by `x_event_type`; enforces uniqueness and presence of `x_event_type`.

### `core.schema_validate`
JSON schema validation conveniences that surface first validation error and schema identifiers.

- **ValidationResult(ok, error=None, schema_id=None)**: Indicates validation success, error message, and schema ID when available.
- `_validate(schema, instance) -> ValidationResult`: Runs `Draft202012Validator` with `FormatChecker`; returns first error message ordered by instance path.
- `validate_envelope(reg, envelope) -> ValidationResult`: Validates an envelope against registry envelope schema.
- `validate_payload(reg, event_type, payload) -> ValidationResult`: Validates payload against schema mapped to `event_type`; returns error if missing schema.

### `core.state_machine`
Defines allowed backlog status transitions and enforcement helpers.

- **BacklogStatus**: States `CREATED`, `READY`, `BLOCKED`, `IN_PROGRESS`, `DONE`, `FAILED`.
- `_ALLOWED`: Dict mapping each state to allowed destination states.
- **TransitionResult(ok, from_status, to_status, reason=None)**: Outcome container for transitions.
- `is_allowed(from_status, to_status) -> bool`: Membership check in `_ALLOWED`.
- `assert_transition(from_status, to_status) -> TransitionResult`: Returns success result for valid transitions; raises `ValueError` with descriptive message otherwise.

### `core.agent_workers`
Shared computation helpers leveraged by the EPIC5 worker agents.

- `normalize_text(text) -> str`: Lowercase, strip punctuation, condense whitespace, and trim for clustering/fingerprinting.
- `compute_time_metrics(work_context) -> (float, float, List[dict])`: Aggregate estimated minutes from `work_context.rows`, compute hours and per-category shares/breakdown.
- `compute_confidence(work_context) -> float`: Score starting at 0.6 then adjust for hourly rate presence, number of rows, category diversity, and missing estimates; clamps to [0,1].
- `compute_costs(total_hours, work_context) -> dict`: Multiply hours by `hourly_rate` and project monthly/annual cost (annual assumes monthly type or defaults to x12).
- `compute_friction(work_context) -> dict`: Cluster rows by normalized text fingerprint to find recurring tasks, derive recurring share and avoidable percentage, and list clusters with counts and sample text.
- `compute_scenario(total_hours, costs, friction) -> dict`: Use friction avoidable percent to compute recovered hours and monetary savings plus a summary string.

### `services.orchestrator.main`
Consumes inbound events, seeds backlogs, handles clarifications, and dispatches READY work.

- `envelope(event_type, payload, source, correlation_id, causation_id, event_version=1) -> dict`: Local envelope builder aligning with regression expectations (service/instance fields use source).
- `_backlog_template(project_id) -> List[dict]`: Creates deterministic set of three READY tasks per project with unique IDs and evidence placeholders.
- `_needs_clarification(item, request_text) -> (bool, str)`: Flags insufficient or ambiguous intake requests; returns reason string.
- `_apply_status_safe(store, project_id, item_id, new_status) -> (bool, str)`: Attempts status update via `assert_transition`; returns success flag and error text without raising.
- `_dlq(r, reason, original_fields, schema_id=None) -> None`: Publishes DLQ entries (leveraging `publish_dlq`) while extracting event metadata when possible.
- `_now_iso() -> str`: Timestamp helper matching worker-generated events.
- `process_message(r, reg, store, qstore, settings, group, msg_id, fields) -> None`: Handles stream messages by parsing/validating envelopes, enforcing idempotence, executing business logic for `PROJECT.INITIAL_REQUEST_RECEIVED` (seed backlog, create questions, dispatch READY items) and `USER.ANSWER_SUBMITTED` (store answer, unblock task, dispatch). DLQs and ACKs on validation or handler errors.
- `_dispatch_ready_tasks(r, settings, store, correlation_id, causation_id) -> int`: Iterates READY tasks across projects, emits `WORK.ITEM_DISPATCHED`, transitions items to `IN_PROGRESS` when possible, and returns the number dispatched.
- `main() -> None`: Sets up logging, settings, registry, Redis client, consumer group, stores, and enters polling loop using `read_group`, delegating each message to `process_message`.

### `services.stream_consumer.main`
Lightweight consumer focused solely on validating incoming events and DLQ-ing failures.

- `process(reg, fields) -> None`: Parses `event` field, validates envelope and payload, and raises exceptions on any validation failure.
- `main() -> None`: Initializes settings, logging, registry, Redis client, and consumer group; loops over `read_group`, invoking `process`; DLQs and ACKs on errors.

### `services.worker.main`
Processes dispatched work items by emitting started/completed events and updating backlog status.

- `_handle_dispatch(r, reg, settings, store, env) -> None`: Validates payload, transitions backlog item to `IN_PROGRESS`, emits `WORK.ITEM_STARTED` and `WORK.ITEM_COMPLETED` events with evidence, and attempts to mark the item `DONE`.
- `_process_message(r, reg, settings, store, msg_id, fields) -> None`: Stream handler that validates envelope, filters for `WORK.ITEM_DISPATCHED`, delegates to `_handle_dispatch`, and DLQs on parsing/validation failures.
- `main() -> None`: Initializes settings, logging, registry, Redis client, and backlog store; ensures consumer group; loops over `read_group`, processing each message.

### `services.time_waste_worker.main`
Agent that turns `WORK.ITEM_DISPATCHED` tasks targeted to `time_waste_worker` into time waste analysis deliverables.

- Validates envelope/payload and ignores other event types or agent targets; enforces idempotence using `event_id` + group key.
- `_emit_clarification` sends `CLARIFICATION.NEEDED` when `work_context.rows` is absent/empty, listing missing fields.
- On valid context, emits `WORK.ITEM_STARTED`, then `_emit_deliverable` publishes `DELIVERABLE.PUBLISHED` summarizing total minutes/hours and breakdown plus `WORK.ITEM_COMPLETED` evidence keyed by totals.

### `services.cost_worker.main`
Agent that estimates cost impact from dispatched agent tasks.

- Validates envelope/payload and agent target; deduplicates with idempotence key.
- If `hourly_rate` or `rows` missing, emits `CLARIFICATION.NEEDED` enumerating missing fields.
- Otherwise emits started event and publishes deliverable with total hours, hourly rate, and monthly/annual costs, followed by completion evidence capturing the computed costs.

### `services.friction_worker.main`
Agent that detects recurring work to quantify friction.

- Validates dispatches targeted to `friction_worker` and uses idempotence guard.
- Requests clarification when no `rows` are supplied.
- Emits started event, computes friction metrics (recurring share, avoidable percent, clusters) and total hours, publishes deliverable, and records completion evidence with friction stats.

### `services.scenario_worker.main`
Agent that projects savings scenarios based on friction and cost.

- Validates dispatches for `scenario_worker`, enforcing idempotence.
- Emits clarification if either `hourly_rate` or `rows` are missing.
- When context is sufficient, emits started event then combines time, friction, and cost computations into a `with_agent_scenario` deliverable and completion evidence highlighting recovered hours and monetary savings.

### `agent_manager`
Coordinates multi-phase agent workflows with persistence, timeout enforcement, and incident handling hooks.

- **Phase**: Enumerates ordered workflow phases (`ANALYZE`, `ARCHITECTURE`, `CODE`, `REVIEW`).
- **PhaseState(phase, message_id, timestamp)**: Captures the last executed phase and when it occurred.
- **StateJournal(redis_client=None, redis_hash_key="agent_manager:state", journal_path=".agent_manager_journal.jsonl")**:
  - `record(state) -> None`: Best-effort persistence of phase state to Redis hash and append-only JSONL file.
  - `clear() -> None`: Remove persisted Redis hash and local journal file when workflow completes.
  - `last_known_state() -> PhaseState | None`: Attempt to recover most recent state from Redis first, then local journal; returns `None` on failure.
- **AgentManager(redis_client, settings, republish_handler=None, incident_handler=None, journal=None)**:
  - `_timeout_for_phase(phase) -> int`: Map phase to configured timeout seconds.
  - `_execute_with_timeout(func, timeout_s) -> (bool, str | None)`: Run callable in thread pool with timeout; returns success flag and failure reason (`"timeout"` or exception message).
  - `_persist_phase(phase, message_id) -> None`: Persist phase progress via journal.
  - `_handle_failure(phase, message_id, reason) -> None`: On timeout, optionally republish; otherwise invoke incident handler and log.
  - `_run_phase(phase, func, message_id) -> bool`: Persist, execute with timeout, and handle failures.
  - `_run_review_with_retry(func, message_id) -> bool`: Retry review phase up to configured attempts before incident handling.
  - `run_workflow(message_id, phases: Dict[Phase, Callable[[], None]]) -> bool`: Execute handlers in order (ANALYZE → ARCHITECTURE → CODE → REVIEW with retry) stopping on failure; clears journal on full success.

### `demo` helpers
Interactive scripts for manual testing and demonstrations using the same stream contracts.

- **interactive_demo.py**: Provides menu-driven actions to send intake events, dispatch requests, simulate worker started/completed events (with or without evidence), inject invalid envelopes, view DLQ entries, and list backlog keys.
- **seed_events.py**: Seeds a single `PROJECT.INITIAL_REQUEST_RECEIVED` envelope with sample payload for quick bootstrapping.
- **clarification_demo.py**: Lists open questions for a project via `QuestionStore`, prompts for an answer, and emits `USER.ANSWER_SUBMITTED` events.

