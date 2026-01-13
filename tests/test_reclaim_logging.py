import logging

from core.redis_streams import read_group


class StubRedis:
    def __init__(self):
        self.read_calls = 0
        self.claim_calls = 0

    def xreadgroup(self, group, consumer, streams, count=1, block=None):
        self.read_calls += 1
        return []

    def xautoclaim(self, **kwargs):
        self.claim_calls += 1
        raise RuntimeError("boom")


def test_reclaim_failure_logged_and_read_continues(caplog):
    stub = StubRedis()
    caplog.set_level(logging.ERROR)

    msgs = read_group(
        stub,
        stream="audit:events",
        group="g1",
        consumer="c1",
        reclaim_min_idle_ms=1,
    )

    assert msgs == []
    assert stub.read_calls == 1
    assert stub.claim_calls == 1
    assert any("Failed to reclaim pending messages" in rec.message for rec in caplog.records)
