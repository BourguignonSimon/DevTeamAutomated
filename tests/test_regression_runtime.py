import json
import time
import uuid

from core.redis_streams import ensure_consumer_group, read_group, ack
from core.event_utils import envelope


def test_pending_is_reclaimed(redis_client):
    stream = "audit:pending:test"
    group = "g1"
    redis_client.delete(stream)
    ensure_consumer_group(redis_client, stream, group)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": "p-" + str(uuid.uuid4())[:6], "request_text": "x"},
        instance="tests-1",
    )
    redis_client.xadd(stream, {"event": json.dumps(env)})

    # consumer1 reads but does NOT ack (simulating crash)
    msgs = read_group(redis_client, stream=stream, group=group, consumer="c1", block_ms=100, count=1)
    assert msgs
    msg_id, _fields = msgs[0]

    # wait for idle threshold then reclaim as consumer2
    time.sleep(0.2)
    reclaimed = read_group(
        redis_client,
        stream=stream,
        group=group,
        consumer="c2",
        block_ms=100,
        count=1,
        reclaim_min_idle_ms=1,  # 1ms
        reclaim_count=10,
    )
    assert reclaimed
    rec_id, _ = reclaimed[0]
    # ack reclaimed
    ack(redis_client, stream, group, rec_id)

    # nothing pending now
    pending = redis_client.xpending(stream, group)
    assert pending["pending"] == 0


def test_smoke_100_events_no_dlq_blowup(redis_client):
    stream = "audit:events"
    dlq = "audit:dlq"
    # inject 100 valid intake events (unique projects)
    before = redis_client.xlen(dlq)
    for i in range(100):
        pid = f"smk-{i}-{str(uuid.uuid4())[:6]}"
        env = envelope(
            event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
            source="tests",
            payload={"project_id": pid, "request_text": "Audit"},
            instance="tests-1",
        )
        redis_client.xadd(stream, {"event": json.dumps(env)})

    # Give the orchestrator time to consume without exploding
    time.sleep(2.0)
    after = redis_client.xlen(dlq)
    # we tolerate 0 DLQ for valid events
    assert after == before
