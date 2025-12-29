import os
import time
import json
import uuid
import pytest
import redis


@pytest.fixture(scope="session")
def redis_client():
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    r = redis.Redis(host=host, port=port, decode_responses=True)
    # ensure clean streams
    r.delete("audit:events")
    r.delete("audit:dlq")
    return r


def wait_for(predicate, timeout_s: float = 5.0, interval_s: float = 0.2):
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval_s)
    return False
