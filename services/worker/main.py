from __future__ import annotations

import json
import logging
import uuid

from core.backlog_store import BacklogStore
from core.config import Settings
from core.dlq import publish_dlq
from core.event_utils import envelope, now_iso
from core.logging import setup_logging
from core.redis_streams import ack, build_redis_client, ensure_consumer_group, read_group
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload
from core.state_machine import BacklogStatus, assert_transition

log = logging.getLogger("worker")


def _handle_dispatch(r, reg, settings, store: BacklogStore, env: dict) -> None:
    payload = env.get("payload", {})
    res_pl = validate_payload(reg, env["event_type"], payload)
    if not res_pl.ok:
        raise ValueError(res_pl.error or "invalid payload")

    project_id = payload["project_id"]
    item_id = payload["backlog_item_id"]

    try:
        current = store.get_item(project_id, item_id)
        if current:
            assert_transition(current.get("status"), BacklogStatus.IN_PROGRESS.value)
            store.set_status(project_id, item_id, BacklogStatus.IN_PROGRESS.value)
    except Exception as e:
        log.warning("unable to mark in-progress: %s", e)

    started_env = envelope(
        event_type="WORK.ITEM_STARTED",
        payload={"project_id": project_id, "backlog_item_id": item_id, "started_at": now_iso()},
        source="worker",
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(started_env)})

    evidence = {"note": "auto-completed"}
    completed_env = envelope(
        event_type="WORK.ITEM_COMPLETED",
        payload={"project_id": project_id, "backlog_item_id": item_id, "evidence": evidence},
        source="worker",
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(completed_env)})

    try:
        current = store.get_item(project_id, item_id)
        if current:
            assert_transition(current.get("status"), BacklogStatus.DONE.value)
            store.set_status(project_id, item_id, BacklogStatus.DONE.value)
    except Exception as e:
        log.warning("unable to mark done: %s", e)


def _process_message(r, reg, settings, store: BacklogStore, msg_id: str, fields: dict) -> None:
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

    event_type = env.get("event_type")
    if event_type != "WORK.ITEM_DISPATCHED":
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    try:
        _handle_dispatch(r, reg, settings, store, env)
    except Exception as e:
        publish_dlq(r, settings.dlq_stream, str(e), fields)

    ack(r, settings.stream_name, settings.consumer_group, msg_id)


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    reg = load_registry("/app/schemas")
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)
    store = BacklogStore(r)

    ensure_consumer_group(r, settings.stream_name, settings.consumer_group)
    log.info("worker listening stream=%s group=%s consumer=%s", settings.stream_name, settings.consumer_group, settings.consumer_name)

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
            _process_message(r, reg, settings, store, msg_id, fields)


if __name__ == "__main__":
    main()
