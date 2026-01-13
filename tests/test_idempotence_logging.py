import logging

from core.idempotence import mark_if_new


def test_duplicate_detection_logged(redis_client, caplog):
    caplog.set_level(logging.INFO)
    assert mark_if_new(redis_client, event_id="evt-1", consumer_group="g1")
    caplog.clear()

    assert not mark_if_new(redis_client, event_id="evt-1", consumer_group="g1", correlation_id="corr-1")
    assert any(
        "Idempotence reject" in rec.message and getattr(rec, "event_id", None) == "evt-1" for rec in caplog.records
    )
