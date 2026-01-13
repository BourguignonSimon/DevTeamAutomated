from core.trace import TraceLogger, TraceRecord


def test_trace_logger_roundtrip():
    logger = TraceLogger()
    rec = TraceRecord(
        agent="dev_worker",
        event_type="WORK.ITEM_COMPLETED",
        decision="validated",
        inputs={"foo": 1},
        outputs={"bar": 2},
        correlation_id="corr",
    )
    logger.log(rec)
    stored = logger.fetch("dev_worker")
    assert stored[0]["decision"] == "validated"
    assert stored[0]["inputs"]["foo"] == 1
