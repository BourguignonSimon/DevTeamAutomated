import json
import uuid

from core.event_utils import envelope
from core.question_store import QuestionStore
from core.backlog_store import BacklogStore
from core.state_machine import BacklogStatus


def test_epic3_blocks_and_unblocks(redis_client):
    r = redis_client
    stream = "audit:events"

    # clean question keys
    for k in r.keys("audit:project:*:questions:*"):
        r.delete(k)
    for k in r.keys("audit:project:*:question:*"):
        r.delete(k)
    for k in r.keys("audit:question:*:answer"):
        r.delete(k)

    project_id = str(uuid.uuid4())
    corr = str(uuid.uuid4())

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        event_version=1,
        source="tests",
        payload={"project_id": project_id, "request_text": "Need audit KPIs for ops"},
        correlation_id=corr,
        causation_id=None,
    )
    r.xadd(stream, {"event": json.dumps(env)})

    bs = BacklogStore(r)
    qs = QuestionStore(r)

    # Wait until a question is created and marked open
    from tests.conftest import wait_for

    assert wait_for(lambda: len(qs.list_open(project_id)) >= 1, timeout_s=8.0)

    qid = qs.list_open(project_id)[0]
    q = qs.get_question(project_id, qid)
    assert q is not None

    item_id = q["backlog_item_id"]
    item = bs.get_item(project_id, item_id)
    assert item is not None
    assert item["status"] == BacklogStatus.BLOCKED.value

    # Submit an answer
    ans_env = envelope(
        event_type="USER.ANSWER_SUBMITTED",
        event_version=1,
        source="tests",
        payload={"project_id": project_id, "question_id": qid, "answer": "Details provided"},
        correlation_id=corr,
        causation_id=None,
    )
    r.xadd(stream, {"event": json.dumps(ans_env)})

    assert wait_for(lambda: bs.get_item(project_id, item_id)["status"] == BacklogStatus.READY.value, timeout_s=8.0)

    # Question should be closed (not open anymore)
    assert qid not in qs.list_open(project_id)

    # Backlog should have stored clarifications in evidence
    item2 = bs.get_item(project_id, item_id)
    assert "clarifications" in (item2.get("evidence") or {})
    assert qid in item2["evidence"]["clarifications"]
