from __future__ import annotations

import logging
import os
import time

import redis

log = logging.getLogger(__name__)

_DEFAULT_PREFIX = os.getenv("IDEMPOTENCE_PREFIX", "audit:processed")


def _key(prefix: str, consumer_group: str, event_id: str) -> str:
    return f"{prefix}:{consumer_group}:{event_id}"


def mark_if_new(
    r: redis.Redis,
    *,
    event_id: str,
    consumer_group: str = "default",
    ttl_s: int = 7 * 24 * 3600,
    prefix: str = _DEFAULT_PREFIX,
    correlation_id: str | None = None,
) -> bool:
    """Return True if event_id was NOT seen before and is now marked as processed.

    Uses SET NX with TTL to be safe across restarts and avoids unbounded sets.
    """
    key = _key(prefix, consumer_group, event_id)
    res = r.set(name=key, value=str(int(time.time())), nx=True, ex=ttl_s)
    if not res:
        log.info(
            "Idempotence reject",
            extra={
                "event_id": event_id,
                "consumer_group": consumer_group,
                "correlation_id": correlation_id,
            },
        )
    return bool(res)


def is_processed(r: redis.Redis, *, consumer_group: str, event_id: str, prefix: str = _DEFAULT_PREFIX) -> bool:
    return bool(r.exists(_key(prefix, consumer_group, event_id)))


def mark_processed(
    r: redis.Redis,
    *,
    consumer_group: str,
    event_id: str,
    ttl_s: int,
    prefix: str = _DEFAULT_PREFIX,
) -> None:
    r.set(_key(prefix, consumer_group, event_id), str(int(time.time())), ex=ttl_s)
