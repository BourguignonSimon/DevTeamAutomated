from __future__ import annotations

import json
import logging

from core.config import Settings
from core.logging import setup_logging
from core.redis_streams import build_redis_client, ensure_consumer_group, read_group, ack
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload
from core.dlq import publish_dlq

log = logging.getLogger("stream_consumer")


def process(reg, fields: dict) -> None:
    if "event" not in fields:
        raise ValueError("missing field event")
    env = json.loads(fields["event"])
    res_env = validate_envelope(reg, env)
    if not res_env.ok:
        raise ValueError(res_env.error or "invalid envelope")
    event_type = env["event_type"]
    payload = env.get("payload")
    res_pl = validate_payload(reg, event_type, payload)
    if not res_pl.ok:
        raise ValueError(res_pl.error or "invalid payload")


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    reg = load_registry("/app/schemas")
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)

    ensure_consumer_group(r, settings.stream_name, settings.consumer_group)
    log.info("listening stream=%s group=%s", settings.stream_name, settings.consumer_group)

    while True:
        msgs = read_group(r, stream=settings.stream_name, group=settings.consumer_group, consumer=settings.consumer_name, block_ms=settings.xread_block_ms, reclaim_min_idle_ms=settings.pending_reclaim_min_idle_ms, reclaim_count=settings.pending_reclaim_count)
        if not msgs:
            continue
        for msg_id, fields in msgs:
            try:
                process(reg, fields)
                ack(r, settings.stream_name, settings.consumer_group, msg_id)
            except Exception as e:
                log.exception("invalid event")
                publish_dlq(r, settings.dlq_stream, str(e), fields)
                ack(r, settings.stream_name, settings.consumer_group, msg_id)


if __name__ == "__main__":
    main()
