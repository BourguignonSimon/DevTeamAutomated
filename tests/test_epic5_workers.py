import json
import os
import uuid

from core.event_utils import envelope
from core.redis_streams import ensure_consumer_group
from core.schema_registry import load_registry
from services.time_waste_worker import main as time_waste_worker
from services.cost_worker import main as cost_worker
from services.friction_worker import main as friction_worker
from services.scenario_worker import main as scenario_worker


def _dispatch_event(agent_target: str, work_context: dict):
    project_id = str(uuid.uuid4())
    backlog_item_id = str(uuid.uuid4())
    env = envelope(
        event_type="WORK.ITEM_DISPATCHED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "item_type": "AGENT_TASK",
            "agent_target": agent_target,
            "work_context": work_context,
        },
        source="tests",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )
    return env, project_id, backlog_item_id


def _set_consumer_env(group: str, name: str = "test-consumer"):
    os.environ["CONSUMER_GROUP"] = group
    os.environ["CONSUMER_NAME"] = name


def _find_event(redis_client, event_type: str, project_id: str, backlog_item_id: str) -> bool:
    for _, fields in redis_client.xrevrange("audit:events", count=200):
        raw = fields.get("event")
        if not raw:
            continue
        data = json.loads(raw)
        if data.get("event_type") != event_type:
            continue
        payload = data.get("payload", {})
        if payload.get("project_id") == project_id and payload.get("backlog_item_id") == backlog_item_id:
            return True
    return False


def test_workers_complete_happy_path(redis_client):
    reg = load_registry("schemas")

    work_context = {
        "rows": [
            {"category": "ops", "estimated_minutes": 30, "text": "Ticket triage"},
            {"category": "ops", "estimated_minutes": 45, "text": "Ticket triage"},
            {"category": "meetings", "estimated_minutes": 60, "text": "status meeting"},
        ],
        "hourly_rate": 100,
        "period": {"type": "monthly", "working_days": 20},
    }

    # time waste
    _set_consumer_env("time_waste_workers", "tw-1")
    tw_settings = time_waste_worker.Settings()
    ensure_consumer_group(redis_client, tw_settings.stream_name, tw_settings.consumer_group)
    env, proj, item = _dispatch_event(time_waste_worker.AGENT_NAME, work_context)
    time_waste_worker._process_message(redis_client, reg, tw_settings, "1-0", {"event": json.dumps(env)})

    # cost
    _set_consumer_env("cost_workers", "cost-1")
    cost_settings = cost_worker.Settings()
    ensure_consumer_group(redis_client, cost_settings.stream_name, cost_settings.consumer_group)
    env2, proj2, item2 = _dispatch_event(cost_worker.AGENT_NAME, work_context)
    cost_worker._process_message(redis_client, reg, cost_settings, "2-0", {"event": json.dumps(env2)})

    # friction
    _set_consumer_env("friction_workers", "fric-1")
    fric_settings = friction_worker.Settings()
    ensure_consumer_group(redis_client, fric_settings.stream_name, fric_settings.consumer_group)
    env3, proj3, item3 = _dispatch_event(friction_worker.AGENT_NAME, work_context)
    friction_worker._process_message(redis_client, reg, fric_settings, "3-0", {"event": json.dumps(env3)})

    # scenario
    _set_consumer_env("scenario_workers", "sc-1")
    scen_settings = scenario_worker.Settings()
    ensure_consumer_group(redis_client, scen_settings.stream_name, scen_settings.consumer_group)
    env4, proj4, item4 = _dispatch_event(scenario_worker.AGENT_NAME, work_context)
    scenario_worker._process_message(redis_client, reg, scen_settings, "4-0", {"event": json.dumps(env4)})

    assert _find_event(redis_client, "DELIVERABLE.PUBLISHED", proj, item)
    assert _find_event(redis_client, "WORK.ITEM_COMPLETED", proj, item)

    assert _find_event(redis_client, "DELIVERABLE.PUBLISHED", proj2, item2)
    assert _find_event(redis_client, "WORK.ITEM_COMPLETED", proj2, item2)

    assert _find_event(redis_client, "DELIVERABLE.PUBLISHED", proj3, item3)
    assert _find_event(redis_client, "WORK.ITEM_COMPLETED", proj3, item3)

    assert _find_event(redis_client, "DELIVERABLE.PUBLISHED", proj4, item4)
    assert _find_event(redis_client, "WORK.ITEM_COMPLETED", proj4, item4)


def test_cost_worker_requests_clarification(redis_client):
    reg = load_registry("schemas")
    _set_consumer_env("cost_workers", "cost-clar")
    settings = cost_worker.Settings()
    ensure_consumer_group(redis_client, settings.stream_name, settings.consumer_group)

    work_context = {"rows": [{"estimated_minutes": 15, "text": "review"}]}
    env, proj, item = _dispatch_event(cost_worker.AGENT_NAME, work_context)
    cost_worker._process_message(redis_client, reg, settings, "10-0", {"event": json.dumps(env)})

    assert _find_event(redis_client, "CLARIFICATION.NEEDED", proj, item)
    assert not _find_event(redis_client, "WORK.ITEM_COMPLETED", proj, item)


def test_invalid_payload_goes_to_dlq(redis_client):
    reg = load_registry("schemas")
    _set_consumer_env("time_waste_workers", "tw-dlq")
    settings = time_waste_worker.Settings()
    ensure_consumer_group(redis_client, settings.stream_name, settings.consumer_group)

    bad_env = {"event_type": "WORK.ITEM_DISPATCHED", "event_version": 1, "payload": {"project_id": "x"}}
    before = redis_client.xlen(settings.dlq_stream)
    time_waste_worker._process_message(redis_client, reg, settings, "11-0", {"event": json.dumps(bad_env)})

    assert redis_client.xlen(settings.dlq_stream) > before
