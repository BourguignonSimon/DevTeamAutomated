import json
import uuid
import threading

from core.event_utils import envelope
from core.backlog_store import BacklogStore
from core.locks import release_lock
from services.orchestrator.main import _dispatch_ready_tasks
from tests.conftest import wait_for

STREAM = "audit:events"
DLQ = "audit:dlq"


def _count_event_type(redis_client, event_type: str) -> int:
    cnt = 0
    for _id, fields in redis_client.xrange(STREAM):
        ev = json.loads(fields["event"])
        if ev.get("event_type") == event_type:
            cnt += 1
    return cnt


def test_backlog_generation_contains_required_fields(redis_client):
    project_id = "gen-" + str(uuid.uuid4())[:8]
    store = BacklogStore(redis_client)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": project_id, "request_text": "Audit my ops"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(env)})

    assert wait_for(lambda: len(store.list_item_ids(project_id)) >= 3, timeout_s=8.0)
    items = list(store.iter_items(project_id))
    # must have fields id, project_id, kind, status, created_at
    for it in items:
        for k in ["id", "project_id", "kind", "status", "created_at"]:
            assert k in it


def test_index_by_status_updates(redis_client):
    project_id = "idx-" + str(uuid.uuid4())[:8]
    store = BacklogStore(redis_client)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": project_id, "request_text": "Audit"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(env)})
    assert wait_for(lambda: len(store.list_item_ids_by_status(project_id, "READY")) > 0, timeout_s=8.0)

    ready_ids = store.list_item_ids_by_status(project_id, "READY")
    assert ready_ids  # index exists

    # take one READY, move to IN_PROGRESS via WORK.ITEM_STARTED after dispatch
    # We force dispatch using orchestrator helper to avoid relying on timing
    _dispatch_ready_tasks(
        redis_client, store, project_id, correlation_id=str(uuid.uuid4()), causation_id=str(uuid.uuid4())
    )
    assert wait_for(lambda: _count_event_type(redis_client, "WORK.ITEM_DISPATCHED") > 0, timeout_s=3.0)

    dispatched = None
    for _id, fields in redis_client.xrange(STREAM):
        ev = json.loads(fields["event"])
        if ev.get("event_type") == "WORK.ITEM_DISPATCHED" and ev["payload"]["project_id"] == project_id:
            dispatched = ev["payload"]["backlog_item_id"]
            break
    assert dispatched

    start = envelope(
        event_type="WORK.ITEM_STARTED",
        source="tests",
        payload={"project_id": project_id, "backlog_item_id": dispatched},
        correlation_id=str(uuid.uuid4()),
        causation_id=str(uuid.uuid4()),
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(start)})

    assert wait_for(lambda: dispatched in store.list_item_ids_by_status(project_id, "IN_PROGRESS"), timeout_s=8.0)


def test_zero_business_exception_invalid_start_is_refused_not_dlq(redis_client):
    # START on non-dispatched item should be refused (business rule), but must not go to DLQ
    project_id = "biz-" + str(uuid.uuid4())[:8]
    store = BacklogStore(redis_client)

    # create backlog
    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": project_id, "request_text": "Audit"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(env)})
    assert wait_for(lambda: len(store.list_item_ids(project_id)) > 0, timeout_s=8.0)

    any_task = next(iter(store.iter_items_by_status(project_id, "READY")))["id"]

    # send START without dispatch
    start = envelope(
        event_type="WORK.ITEM_STARTED",
        source="tests",
        payload={"project_id": project_id, "backlog_item_id": any_task},
        instance="tests-1",
    )
    dlq_before = redis_client.xlen(DLQ)
    redis_client.xadd(STREAM, {"event": json.dumps(start)})

    # should not add DLQ
    assert wait_for(lambda: True, timeout_s=1.0)
    assert redis_client.xlen(DLQ) == dlq_before


def test_locking_concurrent_dispatch_only_one_event(redis_client):
    project_id = "lock-" + str(uuid.uuid4())[:8]
    store = BacklogStore(redis_client)

    env = envelope(
        event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
        source="tests",
        payload={"project_id": project_id, "request_text": "Audit"},
        instance="tests-1",
    )
    redis_client.xadd(STREAM, {"event": json.dumps(env)})
    assert wait_for(lambda: len(store.list_item_ids_by_status(project_id, "READY")) > 0, timeout_s=8.0)

    # call dispatch twice concurrently
    def run():
        _dispatch_ready_tasks(
            redis_client, store, project_id, correlation_id=str(uuid.uuid4()), causation_id=str(uuid.uuid4())
        )

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert wait_for(lambda: _count_event_type(redis_client, "WORK.ITEM_DISPATCHED") >= 1, timeout_s=3.0)
    # only one dispatched for this project (lock)
    dispatched = []
    for _id, fields in redis_client.xrange(STREAM):
        ev = json.loads(fields["event"])
        if ev.get("event_type") == "WORK.ITEM_DISPATCHED" and ev["payload"]["project_id"] == project_id:
            dispatched.append(ev["payload"]["backlog_item_id"])
    assert len(dispatched) == 1
