from __future__ import annotations

import redis


def mark_if_new(
    r: redis.Redis,
    *,
    event_id: str,
    ttl_s: int = 7 * 24 * 3600,
    prefix: str = "audit:processed:event",
) -> bool:
    """Return True if event_id was NOT seen before and is now marked as processed.

    Uses SET NX with TTL to be safe across restarts and avoids unbounded sets.
    """
    key = f"{prefix}:{event_id}"
    res = r.set(name=key, value="1", nx=True, ex=ttl_s)
    return bool(res)
