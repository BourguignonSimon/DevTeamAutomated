from __future__ import annotations

import time
import redis


def acquire_lock(r: redis.Redis, key: str, ttl_s: int = 120) -> bool:
    # SET key value NX EX ttl
    value = str(time.time())
    return bool(r.set(key, value, nx=True, ex=ttl_s))


def release_lock(r: redis.Redis, key: str) -> None:
    r.delete(key)
