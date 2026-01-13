import logging

from core.locks import RedisLock, acquire_lock, release_lock


def test_acquire_lock_returns_token_and_ttl(redis_client):
    lock = acquire_lock(redis_client, "lock:test", ttl_ms=5000)
    assert lock is not None
    assert redis_client.get("lock:test") == lock.token
    assert redis_client.pttl("lock:test") > 0
    assert release_lock(redis_client, lock)


def test_release_with_wrong_token_does_not_delete(redis_client, caplog):
    caplog.set_level(logging.INFO)
    lock = acquire_lock(redis_client, "lock:test2", ttl_ms=5000)
    assert lock is not None

    wrong = RedisLock(key="lock:test2", token="bogus")
    assert release_lock(redis_client, wrong) is False
    assert redis_client.get("lock:test2") == lock.token
    assert any("token mismatch" in rec.message for rec in caplog.records)


def test_second_acquire_returns_none(redis_client):
    first = acquire_lock(redis_client, "lock:test3", ttl_ms=1000)
    assert first is not None
    second = acquire_lock(redis_client, "lock:test3", ttl_ms=1000)
    assert second is None
