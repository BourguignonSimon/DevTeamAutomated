from __future__ import annotations

import json
import logging
import uuid

from core.agent_workers import compute_confidence, compute_time_metrics
from core.config import Settings
from core.dlq import publish_dlq
from core.event_utils import envelope, now_iso
from core.idempotence import mark_if_new
from core.logging import setup_logging
from core.redis_streams import ack, build_redis_client, ensure_consumer_group, read_group
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload

AGENT_NAME = "time_waste_worker"
log = logging.getLogger(AGENT_NAME)


def _emit_started(r, settings: Settings, env: dict, project_id: str, backlog_item_id: str) -> None:
    started_env = envelope(
        event_type="WORK.ITEM_STARTED",
        payload={"project_id": project_id, "backlog_item_id": backlog_item_id, "started_at": now_iso()},
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(started_env)})


def _emit_deliverable(r, settings: Settings, env: dict, project_id: str, backlog_item_id: str, work_context: dict) -> None:
    total_minutes, total_hours, breakdown = compute_time_metrics(work_context)
    deliverable = {
        "type": "time_waste_analysis",
        "project_id": project_id,
        "backlog_item_id": backlog_item_id,
        "timestamp": now_iso(),
        "confidence": compute_confidence(work_context),
        "agent": AGENT_NAME,
        "content": {
            "total_minutes": total_minutes,
            "total_hours": total_hours,
            "breakdown": breakdown,
        },
    }
    dlv_env = envelope(
        event_type="DELIVERABLE.PUBLISHED",
        payload={"project_id": project_id, "backlog_item_id": backlog_item_id, "deliverable": deliverable},
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(dlv_env)})

    completed_env = envelope(
        event_type="WORK.ITEM_COMPLETED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "evidence": {
                "agent": AGENT_NAME,
                "total_minutes": total_minutes,
                "total_hours": total_hours,
            },
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(completed_env)})


def _emit_clarification(r, settings: Settings, env: dict, project_id: str, backlog_item_id: str, reason: str, missing: list[str]) -> None:
    clar_env = envelope(
        event_type="CLARIFICATION.NEEDED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "reason": reason,
            "missing_fields": missing,
            "agent": AGENT_NAME,
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(clar_env)})


def _process_message(r, reg, settings: Settings, msg_id: str, fields: dict) -> None:
    if "event" not in fields:
        publish_dlq(r, settings.dlq_stream, "missing field 'event'", fields)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    try:
        env = json.loads(fields["event"])
    except Exception as e:
        publish_dlq(r, settings.dlq_stream, f"invalid json: {e}", fields)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    res_env = validate_envelope(reg, env)
    if not res_env.ok:
        publish_dlq(r, settings.dlq_stream, res_env.error or "invalid envelope", fields, schema_id=res_env.schema_id)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    if env.get("event_type") != "WORK.ITEM_DISPATCHED":
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    payload = env.get("payload", {})
    res_pl = validate_payload(reg, env["event_type"], payload)
    if not res_pl.ok:
        publish_dlq(r, settings.dlq_stream, res_pl.error or "invalid payload", fields, schema_id=res_pl.schema_id)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    if payload.get("agent_target") != AGENT_NAME:
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    event_id = env.get("event_id")
    idem_key = f"{event_id}:{settings.consumer_group}"
    if not mark_if_new(r, event_id=idem_key, ttl_s=settings.idempotence_ttl_s, prefix=settings.idempotence_prefix):
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    project_id = payload["project_id"]
    backlog_item_id = payload["backlog_item_id"]
    work_context = payload.get("work_context") or {}

    rows = work_context.get("rows") or []
    if not rows:
        _emit_clarification(r, settings, env, project_id, backlog_item_id, "work_context.rows missing", ["rows"])
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    try:
        _emit_started(r, settings, env, project_id, backlog_item_id)
        _emit_deliverable(r, settings, env, project_id, backlog_item_id, work_context)
    except Exception as e:
        publish_dlq(r, settings.dlq_stream, str(e), fields)

    ack(r, settings.stream_name, settings.consumer_group, msg_id)


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    reg = load_registry("/app/schemas")
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)

    ensure_consumer_group(r, settings.stream_name, settings.consumer_group)
    log.info("%s listening stream=%s group=%s consumer=%s", AGENT_NAME, settings.stream_name, settings.consumer_group, settings.consumer_name)

    while True:
        msgs = read_group(
            r,
            stream=settings.stream_name,
            group=settings.consumer_group,
            consumer=settings.consumer_name,
            block_ms=settings.xread_block_ms,
            reclaim_min_idle_ms=settings.pending_reclaim_min_idle_ms,
            reclaim_count=settings.pending_reclaim_count,
        )
        if not msgs:
            continue

        for msg_id, fields in msgs:
            _process_message(r, reg, settings, msg_id, fields)


if __name__ == "__main__":
    main()
