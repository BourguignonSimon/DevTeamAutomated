from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.backlog_store import BacklogStore
from core.config import Settings
from core.dlq import publish_dlq
from core.failures import Failure, FailureCategory
from core.idempotence import mark_if_new
from core.metrics import MetricsRecorder
from core.project_store import ProjectStore
from core.question_store import QuestionStore
from core.redis_streams import ack, build_redis_client, ensure_consumer_group, read_group
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload
from core.state_machine import BacklogStatus, assert_transition
from core.trace import TraceLogger, TraceRecord
from core.validators import DefinitionOfDoneRegistry, ValidationResult, default_validator

log = logging.getLogger("orchestrator")
trace_logger: TraceLogger | None = None
metrics: MetricsRecorder | None = None
project_store: ProjectStore | None = None
dod_registry = DefinitionOfDoneRegistry()
dod_registry.register("test_worker", default_validator)
dod_registry.register("dev_worker", default_validator)
dod_registry.register("requirements_manager", default_validator)
dod_registry.register("scenario_worker", default_validator)


# ----------------------------
# Envelope helper (matches your tests style)
# ----------------------------
def envelope(
    *,
    event_type: str,
    payload: Dict[str, Any],
    source: str,
    correlation_id: str,
    causation_id: Optional[str],
    event_version: int = 1,
) -> Dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "timestamp": _now_iso(),
        "source": {"service": source, "instance": source},
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "payload": payload,
    }


# ----------------------------
# Backlog + Clarification rules (same spirit as your file)
# ----------------------------
def _backlog_template(project_id: str) -> List[Dict[str, Any]]:
    # Keep deterministic + >= 3 items for regression tests
    return [
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "type": "TASK",
            "title": "Collect requirements",
            "description": "Clarify scope and KPIs",
            "status": BacklogStatus.READY.value,
            "evidence": [],
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "type": "TASK",
            "title": "Run checks",
            "description": "Compute KPIs and anomalies",
            "status": BacklogStatus.READY.value,
            "evidence": [],
        },
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "type": "TASK",
            "title": "Produce report",
            "description": "Generate deliverable",
            "status": BacklogStatus.READY.value,
            "evidence": [],
        },
    ]


def _needs_clarification(item: Dict[str, Any], request_text: str) -> Tuple[bool, str]:
    txt = (request_text or "").strip()
    if len(txt) < 12:
        return True, "Request too short: specify scope and expected KPIs."
    if "kpi" in txt.lower() and "?" not in txt:
        return True, "Which KPIs do you want (SLA, MTTR, backlog aging, incident volume, etc.)?"
    return False, ""


def _apply_status_safe(store: BacklogStore, project_id: str, item_id: str, new_status: BacklogStatus) -> Tuple[bool, str]:
    item = store.get_item(project_id, item_id)
    if not item:
        return False, "missing item"
    try:
        assert_transition(item.get("status"), new_status.value)
        store.set_status(project_id, item_id, new_status.value)
        return True, ""
    except Exception as e:
        return False, str(e)


def _dlq(r, reason: str, original_fields: Any, schema_id: Optional[str] = None, original_event: Optional[Dict[str, Any]] = None) -> None:
    # Ensure original_fields is a dict with string values (Redis stream format)
    if not isinstance(original_fields, dict):
        original_fields = {}
    else:
        # Ensure all values are strings (Redis stream format requirement)
        original_fields = {k: str(v) if not isinstance(v, str) else v for k, v in original_fields.items()}

    # If we have a decoded event but original_fields doesn't have 'event', add it
    # This preserves event metadata even when fields don't contain the event properly
    if original_event and "event" not in original_fields:
        original_fields = original_fields.copy()
        original_fields["event"] = json.dumps(original_event)

    publish_dlq(
        r,
        Settings().dlq_stream,  # safe: reads env defaults
        f"{reason}" + (f" (schema={schema_id})" if schema_id else ""),
        original_fields,
        schema_id=schema_id,
    )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _send_customer_message(
    r,
    settings: Settings,
    pstore: ProjectStore,
    project_id: str,
    message_type: str,
    content: str,
    related_item_id: Optional[str] = None,
    requires_response: bool = False,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    """Send a message to the customer via the web interface.

    This stores the message in the ProjectStore and emits an event
    so that the web gateway can deliver it to the customer.
    """
    # Store the message
    message = pstore.send_message_to_customer(
        project_id=project_id,
        message_type=message_type,
        content=content,
        related_item_id=related_item_id,
        requires_response=requires_response,
    )

    # Emit ORCHESTRATOR.MESSAGE_SENT event
    msg_env = envelope(
        event_type="ORCHESTRATOR.MESSAGE_SENT",
        payload={
            "project_id": project_id,
            "message_id": message.id,
            "message_type": message_type,
            "content": content,
            "related_item_id": related_item_id,
            "requires_response": requires_response,
        },
        source="orchestrator",
        correlation_id=correlation_id or str(uuid.uuid4()),
        causation_id=causation_id,
    )
    r.xadd(settings.stream_name, {"event": json.dumps(msg_env)})
    log.info("Sent customer message %s for project %s", message.id, project_id)


# ----------------------------
# Core consumer logic (mostly your original structure)
# ----------------------------
def process_message(
    r,
    reg,
    store: BacklogStore,
    qstore: QuestionStore,
    pstore: ProjectStore,
    settings: Settings,
    group: str,
    msg_id: str,
    fields: Dict[str, str],
) -> None:
    global trace_logger
    global metrics
    global project_store
    if trace_logger is None:
        trace_logger = TraceLogger(prefix=settings.trace_prefix)
    if metrics is None:
        metrics = MetricsRecorder(prefix=settings.metrics_prefix)
    if project_store is None:
        project_store = pstore
    # parse
    if "event" not in fields:
        _dlq(r, "missing field 'event'", fields)
        ack(r, settings.stream_name, group, msg_id)
        return

    try:
        env = json.loads(fields["event"])
    except Exception as e:
        _dlq(r, f"invalid json: {e}", fields)
        ack(r, settings.stream_name, group, msg_id)
        return

    # schema validation (DLQ only for contract issues)
    res_env = validate_envelope(reg, env)
    if not res_env.ok:
        _dlq(r, res_env.error or "invalid envelope", fields, schema_id=res_env.schema_id)
        ack(r, settings.stream_name, group, msg_id)
        return

    event_type = env["event_type"]
    payload = env.get("payload")

    corr = env.get("correlation_id") or str(uuid.uuid4())
    caus = env.get("event_id")
    event_id = env["event_id"]

    # idempotence
    if not mark_if_new(
        r,
        event_id=event_id,
        consumer_group=settings.consumer_group,
        ttl_s=settings.idempotence_ttl_s,
        prefix=settings.idempotence_prefix,
        correlation_id=corr,
    ):
        log.info("duplicate event ignored event_id=%s", event_id)
        ack(r, settings.stream_name, group, msg_id)
        return

    res_pl = validate_payload(reg, event_type, payload)
    if not res_pl.ok:
        _dlq(r, res_pl.error or "invalid payload", fields, schema_id=res_pl.schema_id)
        ack(r, settings.stream_name, group, msg_id)
        return

    # domain/business logic (no raises)
    try:
        if event_type == "PROJECT.INITIAL_REQUEST_RECEIVED":
            project_id = payload["project_id"]
            request_text = payload.get("request_text") or ""

            for it in _backlog_template(project_id):
                store.put_item(it)

            # Detect ambiguities and block tasks that cannot proceed
            for it in list(store.iter_items(project_id)):
                needs, reason = _needs_clarification(it, request_text)
                if not needs:
                    continue

                ok, _ = _apply_status_safe(store, project_id, it["id"], BacklogStatus.BLOCKED)
                if not ok:
                    continue

                q = qstore.create_question(
                    project_id=project_id,
                    backlog_item_id=it["id"],
                    question_text=reason,
                    answer_type="text",
                    status="OPEN",
                    correlation_id=corr,
                )

                q_env = envelope(
                    event_type="QUESTION.CREATED",
                    payload={"question": q},
                    source="orchestrator",
                    correlation_id=corr,
                    causation_id=caus,
                )
                r.xadd(settings.stream_name, {"event": json.dumps(q_env)})

                c_env = envelope(
                    event_type="CLARIFICATION.NEEDED",
                    payload={
                        "project_id": project_id,
                        "backlog_item_id": it["id"],
                        "question_id": q["id"] if isinstance(q, dict) else getattr(q, "id", None),
                    },
                    source="orchestrator",
                    correlation_id=corr,
                    causation_id=caus,
                )
                r.xadd(settings.stream_name, {"event": json.dumps(c_env)})

            _dispatch_ready_tasks(r, settings, store, corr, caus)

        elif event_type == "USER.ANSWER_SUBMITTED":
            project_id = payload["project_id"]
            question_id = payload["question_id"]
            answer = payload.get("answer")

            qstore.set_answer(project_id, question_id, answer)
            qstore.close_question(project_id, question_id)

            q = qstore.get_question(project_id, question_id)
            backlog_item_id = q.get("backlog_item_id") if isinstance(q, dict) else getattr(q, "backlog_item_id", None)
            if backlog_item_id:
                _apply_status_safe(store, project_id, backlog_item_id, BacklogStatus.READY)

                ub_env = envelope(
                    event_type="BACKLOG.ITEM_UNBLOCKED",
                    payload={"project_id": project_id, "backlog_item_id": backlog_item_id, "question_id": question_id},
                    source="orchestrator",
                    correlation_id=corr,
                    causation_id=caus,
                )
                r.xadd(settings.stream_name, {"event": json.dumps(ub_env)})

                _dispatch_ready_tasks(r, settings, store, corr, caus)

        elif event_type == "WORK.ITEM_COMPLETED":
            project_id = payload["project_id"]
            backlog_item_id = payload["backlog_item_id"]
            agent = env.get("source", {}).get("service") or "unknown"
            metrics.inc("work_item_completed_seen")
            result: ValidationResult = dod_registry.validate(agent, payload)
            if not result.ok:
                reason = result.reason or "dod_failed"
                fail_env = envelope(
                    event_type="WORK.ITEM_FAILED",
                    payload={
                        "project_id": project_id,
                        "backlog_item_id": backlog_item_id,
                        "failure": Failure(FailureCategory.DATA_INSUFFICIENCY, reason).to_payload(),
                    },
                    source="orchestrator",
                    correlation_id=corr,
                    causation_id=caus,
                )
                r.xadd(settings.stream_name, {"event": json.dumps(fail_env)})
                clar_env = envelope(
                    event_type="CLARIFICATION.NEEDED",
                    payload={
                        "project_id": project_id,
                        "backlog_item_id": backlog_item_id,
                        "reason": reason,
                        "agent": agent,
                    },
                    source="orchestrator",
                    correlation_id=corr,
                    causation_id=caus,
                )
                r.xadd(settings.stream_name, {"event": json.dumps(clar_env)})
            else:
                current = store.get_item(project_id, backlog_item_id) if hasattr(store, "get_item") else None
                try:
                    assert_transition((current or {}).get("status"), BacklogStatus.DONE.value)
                except Exception:
                    try:
                        store.set_status(project_id, backlog_item_id, BacklogStatus.DONE.value)
                    except Exception:
                        pass
                trace_logger.log(
                    TraceRecord(
                        agent=agent,
                        event_type=event_type,
                        decision="definition_of_done_passed",
                        inputs={"payload": payload},
                        outputs={"status": "DONE"},
                        correlation_id=corr,
                    )
                )

        elif event_type == "HUMAN.APPROVAL_REQUESTED":
            project_id = payload["project_id"]
            backlog_item_id = payload["backlog_item_id"]
            r.set(f"approval:pending:{project_id}:{backlog_item_id}", "1")
            metrics.inc("human_approval_requested")

        elif event_type == "HUMAN.APPROVAL_SUBMITTED":
            project_id = payload["project_id"]
            backlog_item_id = payload["backlog_item_id"]
            r.delete(f"approval:pending:{project_id}:{backlog_item_id}")
            metrics.inc("human_approval_completed")
            _dispatch_ready_tasks(r, settings, store, corr, caus)

        elif event_type == "USER.PROMPT_SUBMITTED":
            # Handle user prompts from the web interface
            project_id = payload["project_id"]
            prompt = payload.get("prompt", "")
            interaction_id = payload.get("interaction_id")
            context = payload.get("context", [])

            log.info("Processing user prompt for project %s: %s", project_id, prompt[:50])
            metrics.inc("user_prompt_received")

            # Record the interaction in project store
            if pstore:
                pstore.add_interaction(
                    project_id=project_id,
                    interaction_type="system_response",
                    content=f"Received prompt: {prompt[:100]}...",
                    metadata={"interaction_id": interaction_id},
                )

            # Analyze prompt and determine if tasks need to be created or questions answered
            # For now, send acknowledgment message to customer
            if pstore:
                _send_customer_message(
                    r, settings, pstore, project_id,
                    message_type="status_update",
                    content=f"Your request is being processed: {prompt[:100]}...",
                    requires_response=False,
                    correlation_id=corr,
                    causation_id=caus,
                )

            # Check if there are blocked items that need attention
            blocked_items = list(store.iter_items_by_status(project_id, "BLOCKED"))
            if blocked_items:
                # Send clarification request to customer
                for item in blocked_items:
                    open_questions = qstore.list_open(project_id)
                    for qid in open_questions:
                        q = qstore.get_question(project_id, qid)
                        if q and q.get("backlog_item_id") == item["id"]:
                            if pstore:
                                _send_customer_message(
                                    r, settings, pstore, project_id,
                                    message_type="clarification",
                                    content=q.get("question_text", "Clarification needed"),
                                    related_item_id=item["id"],
                                    requires_response=True,
                                    correlation_id=corr,
                                    causation_id=caus,
                                )

        elif event_type == "CUSTOMER.MESSAGE_RESPONDED":
            # Handle customer responses to orchestrator messages
            project_id = payload["project_id"]
            message_id = payload["message_id"]
            response = payload.get("response", "")
            related_item_id = payload.get("related_item_id")

            log.info("Processing customer response for project %s, message %s", project_id, message_id)
            metrics.inc("customer_message_responded")

            # Record the response interaction
            if pstore:
                pstore.add_interaction(
                    project_id=project_id,
                    interaction_type="user_input",
                    content=f"Customer response: {response}",
                    metadata={"message_id": message_id, "related_item_id": related_item_id},
                )

            # If related to a blocked item, try to unblock it
            if related_item_id:
                item = store.get_item(project_id, related_item_id)
                if item and item.get("status") == "BLOCKED":
                    # Check if there's an open question for this item
                    open_questions = qstore.list_open(project_id)
                    for qid in open_questions:
                        q = qstore.get_question(project_id, qid)
                        if q and q.get("backlog_item_id") == related_item_id:
                            # Use the response as the answer
                            qstore.set_answer(project_id, qid, response)
                            qstore.close_question(project_id, qid)
                            _apply_status_safe(store, project_id, related_item_id, BacklogStatus.READY)

                            # Emit unblocked event
                            ub_env = envelope(
                                event_type="BACKLOG.ITEM_UNBLOCKED",
                                payload={
                                    "project_id": project_id,
                                    "backlog_item_id": related_item_id,
                                    "question_id": qid,
                                },
                                source="orchestrator",
                                correlation_id=corr,
                                causation_id=caus,
                            )
                            r.xadd(settings.stream_name, {"event": json.dumps(ub_env)})
                            break

                    # Try to dispatch ready tasks
                    _dispatch_ready_tasks(r, settings, store, corr, caus)

            # Send acknowledgment to customer
            if pstore:
                _send_customer_message(
                    r, settings, pstore, project_id,
                    message_type="status_update",
                    content="Thank you for your response. We're processing your input.",
                    requires_response=False,
                    correlation_id=corr,
                    causation_id=caus,
                )

        # else: ignore other event_types for EPIC3 scope

    except Exception as e:
        # Business failures are not silent: DLQ (keeps pipeline robust)
        # Pass the decoded env if available to preserve event metadata
        _dlq(r, f"handler_error: {e}", fields, original_event=env if 'env' in locals() else None)

    # Always ACK to prevent infinite pending
    ack(r, settings.stream_name, group, msg_id)

def _dispatch_ready_tasks(r, settings, store: "BacklogStore", correlation_id: str, causation_id: str) -> int:
    """
    Minimal dispatcher expected by regression tests.
    - Finds READY backlog items
    - Emits WORK.ITEM_DISPATCHED events
    - Marks items as DISPATCHED (or IN_PROGRESS depending on your state machine)
    Returns number of dispatched items.
    """
    project_ids = store.list_project_ids() if hasattr(store, "list_project_ids") else []

    dispatched = 0
    for project_id in project_ids:
        # Prefer a store helper if it exists
        if hasattr(store, "list_item_ids_by_status"):
            ready_ids = store.list_item_ids_by_status(project_id, "READY")
        else:
            # Fallback: iterate items and filter
            ready_ids = []
            for it in store.iter_items(project_id):
                if (it.get("status") == "READY") and (it.get("type") == "TASK"):
                    ready_ids.append(it["id"])

        for item_id in ready_ids:
            current = store.get_item(project_id, item_id) if hasattr(store, "get_item") else None
            title = (current or {}).get("title") or ""
            title_lower = title.lower()

            if "collect requirements" in title:
                agent_target = "requirements_manager"
            elif "run checks" in title:
                agent_target = "dev_worker"
            elif "produce report" in title or "test" in title_lower:
                agent_target = "test_worker"
            else:
                agent_target = "dev_worker"

            env = {
                "event_id": str(uuid.uuid4()),
                "event_type": "WORK.ITEM_DISPATCHED",
                "event_version": 1,
                "timestamp": _now_iso(),
                "source": {"service": "orchestrator", "instance": settings.consumer_name},
                "correlation_id": correlation_id,
                "causation_id": causation_id,
                "payload": {
                    "project_id": project_id,
                    "backlog_item_id": item_id,
                    "item_type": (current or {}).get("type"),
                    "agent_target": agent_target,
                    "work_context": {"rows": []},
                },
            }
            r.xadd(settings.stream_name, {"event": json.dumps(env)})

            if hasattr(store, "set_status"):
                current = current or store.get_item(project_id, item_id)
                if current:
                    try:
                        assert_transition(current.get("status"), BacklogStatus.IN_PROGRESS.value)
                        store.set_status(project_id, item_id, BacklogStatus.IN_PROGRESS.value)
                    except Exception:
                        pass

            dispatched += 1

    return dispatched

def main() -> None:
    # logging
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    settings = Settings()
    global trace_logger
    global metrics
    trace_logger = TraceLogger(prefix=settings.trace_prefix)
    metrics = MetricsRecorder(prefix=settings.metrics_prefix)

    # registry + redis
    reg = load_registry("/app/schemas")
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)

    # IMPORTANT: use settings for group/consumer (no hardcode)
    group = settings.consumer_group
    consumer = settings.consumer_name

    # Create group + stream if missing
    ensure_consumer_group(r, settings.stream_name, group)

    store = BacklogStore(r, prefix=settings.key_prefix)
    qstore = QuestionStore(r, prefix=settings.key_prefix)
    pstore = ProjectStore(r, prefix=settings.key_prefix)

    log.info("orchestrator listening stream=%s group=%s consumer=%s", settings.stream_name, group, consumer)

    while True:
        # ✅ FIX: proper read_group call (your previous line was broken)
        msgs = read_group(
            r,
            stream=settings.stream_name,
            group=group,
            consumer=consumer,
            block_ms=settings.xread_block_ms,
            reclaim_min_idle_ms=settings.pending_reclaim_min_idle_ms,
            reclaim_count=settings.pending_reclaim_count,
        )
        if not msgs:
            continue

        for msg_id, fields in msgs:
            process_message(
                r,
                reg,
                store,
                qstore,
                pstore,
                settings,
                group,
                msg_id,
                fields,
            )


if __name__ == "__main__":
    main()
