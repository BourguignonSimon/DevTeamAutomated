from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import redis

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedisLock:
    key: str
    token: str


def acquire_lock(r: redis.Redis, key: str, ttl_ms: int = 120_000) -> Optional[RedisLock]:
    """Acquire a Redis-based lock using SET NX PX and return the lock token.

    TTL is always applied to avoid deadlocks. Returns None when the lock is already held.
    """

    token = str(uuid.uuid4())
    ok = r.set(name=key, value=token, nx=True, px=ttl_ms)
    if not ok:
        return None
    return RedisLock(key=key, token=token)


_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


def release_lock(r: redis.Redis, lock: RedisLock) -> bool:
    """Release the lock only if the token matches.

    Returns True when the lock is released, False if it was missing or owned by someone else.
    """

    try:
        res = r.eval(_RELEASE_SCRIPT, 1, lock.key, lock.token)
    except Exception:
        log.exception("Failed to release lock", extra={"key": lock.key})
        return False

    if res == 0:
        log.info("Lock release skipped due to token mismatch", extra={"key": lock.key, "token": lock.token})
        return False
    return True
