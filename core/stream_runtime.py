from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import redis

from core.config import Settings
from core.dlq import publish_dlq
from core.idempotence import is_processed, mark_processed
from core.redis_streams import ensure_consumer_group
from core.schema_registry import SchemaRegistry, load_registry
from core.schema_validate import validate_envelope, validate_payload

log = logging.getLogger(__name__)


@dataclass
class AttemptMeta:
    attempts: int
    first_seen_at: float
    last_seen_at: float


class ReliableStreamProcessor:
    def __init__(
        self,
        r: redis.Redis,
        *,
        settings: Settings,
        handler: Callable[[dict], None],
        registry: SchemaRegistry | None = None,
    ) -> None:
        self.r = r
        self.settings = settings
        self.handler = handler
        self.registry = registry or load_registry("/app/schemas")
        ensure_consumer_group(r, settings.stream_name, settings.consumer_group)

    def _attempt_key(self, msg_id: str) -> str:
        return f"attempts:{self.settings.consumer_group}:{msg_id}"

    def _increment_attempt(self, msg_id: str) -> AttemptMeta:
        key = self._attempt_key(msg_id)
        attempts = int(self.r.hincrby(key, "attempts", 1))
        now = time.time()
        if attempts == 1:
            self.r.hset(key, mapping={"first_seen_at": now, "last_seen_at": now})
        else:
            self.r.hset(key, "last_seen_at", now)
        self.r.expire(key, self.settings.dedupe_ttl_s)
        data = self.r.hgetall(key)
        return AttemptMeta(
            attempts=attempts,
            first_seen_at=float(data.get("first_seen_at", now)),
            last_seen_at=float(data.get("last_seen_at", now)),
        )

    def _send_dlq(
        self, reason: str, fields: Dict[str, str], attempts: AttemptMeta | None = None, error: Exception | None = None
    ):
        publish_dlq(
            self.r,
            self.settings.dlq_stream,
            reason,
            fields,
            error=error,
            consumer_group=self.settings.consumer_group,
            attempts=attempts.attempts if attempts else None,
            first_seen_at=attempts.first_seen_at if attempts else None,
            last_seen_at=attempts.last_seen_at if attempts else None,
        )

    def _process_single(self, msg_id: str, fields: Dict[str, str]) -> None:
        attempt_meta = self._increment_attempt(msg_id)

        if "event" not in fields:
            self._send_dlq("missing field 'event'", fields, attempt_meta)
            self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return
        try:
            env = json.loads(fields["event"])
        except Exception as e:
            self._send_dlq(f"invalid json: {e}", fields, attempt_meta, e)
            self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return

        res_env = validate_envelope(self.registry, env)
        if not res_env.ok:
            self._send_dlq(res_env.error or "invalid envelope", fields, attempt_meta, None)
            self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return

        event_type = env.get("event_type")
        payload = env.get("payload")
        res_pl = validate_payload(self.registry, event_type, payload)
        if not res_pl.ok:
            self._send_dlq(res_pl.error or "invalid payload", fields, attempt_meta, None)
            self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return

        event_id = env.get("event_id")
        if event_id and is_processed(
            self.r,
            consumer_group=self.settings.consumer_group,
            event_id=event_id,
            prefix=self.settings.idempotence_prefix,
        ):
            log.info("skip duplicate event_id=%s group=%s", event_id, self.settings.consumer_group)
            self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return

        try:
            self.handler(env)
        except Exception as e:
            log.exception("handler error event_type=%s msg_id=%s", event_type, msg_id)
            if attempt_meta.attempts >= self.settings.max_attempts:
                self._send_dlq("max attempts exceeded", fields, attempt_meta, e)
                self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)
            return

        if event_id:
            mark_processed(
                self.r,
                consumer_group=self.settings.consumer_group,
                event_id=event_id,
                ttl_s=self.settings.dedupe_ttl_s,
                prefix=self.settings.idempotence_prefix,
            )
        self.r.xack(self.settings.stream_name, self.settings.consumer_group, msg_id)

    def consume_once(self) -> int:
        msgs: List[Tuple[str, Dict[str, str]]] = []
        # prefer new messages
        resp = self.r.xreadgroup(
            self.settings.consumer_group,
            self.settings.consumer_name,
            {self.settings.stream_name: ">"},
            count=10,
            block=self.settings.block_ms,
        )
        if resp:
            _, msgs = resp[0]
        else:
            # reclaim pending
            try:
                _, claimed, _ = self.r.xautoclaim(
                    name=self.settings.stream_name,
                    groupname=self.settings.consumer_group,
                    consumername=self.settings.consumer_name,
                    min_idle_time=self.settings.idle_reclaim_ms,
                    start_id="0-0",
                    count=self.settings.reclaim_count,
                )
                msgs = claimed
            except Exception:
                msgs = []

        for msg_id, fields in msgs:
            self._process_single(msg_id, fields)
        return len(msgs)

    def run_forever(self) -> None:
        while True:
            processed = self.consume_once()
            if processed == 0:
                time.sleep(0.05)
