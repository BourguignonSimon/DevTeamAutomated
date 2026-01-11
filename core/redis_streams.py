from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

import redis

log = logging.getLogger(__name__)


def build_redis_client(host: str, port: int, db: int = 0) -> redis.Redis:
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


def ensure_consumer_group(r: redis.Redis, stream: str, group: str) -> None:
    try:
        r.xgroup_create(stream, group, id="0-0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            return
        raise


def read_group(
    r: redis.Redis,
    *,
    stream: str,
    group: str,
    consumer: str,
    block_ms: int = 2000,
    count: int = 10,
    reclaim_min_idle_ms: Optional[int] = None,
    reclaim_count: int = 50,
) -> List[Tuple[str, Dict[str, str]]]:
    """Read messages for a consumer group.

    1) Prefer new messages (XREADGROUP with '>')
    2) If nothing new and reclaim_min_idle_ms is set, try to reclaim pending messages
       that have been idle for at least reclaim_min_idle_ms using XAUTOCLAIM.

    This supports the regression requirement: no message stays pending forever after a crash.
    """
    resp = r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    if resp:
        _, msgs = resp[0]
        return [(mid, fields) for mid, fields in msgs]

    if reclaim_min_idle_ms is None:
        return []

    # Best effort pending reclaim.
    try:
        next_start, claimed, _deleted = r.xautoclaim(
            name=stream,
            groupname=group,
            consumername=consumer,
            min_idle_time=reclaim_min_idle_ms,
            start_id="0-0",
            count=reclaim_count,
        )
        if not claimed:
            return []
        return [(mid, fields) for mid, fields in claimed]
    except Exception:
        log.exception(
            "Failed to reclaim pending messages",
            extra={"stream": stream, "group": group, "consumer": consumer},
        )
        time.sleep(0.1)
        return []


def ack(r: redis.Redis, stream: str, group: str, msg_id: str) -> None:
    r.xack(stream, group, msg_id)
