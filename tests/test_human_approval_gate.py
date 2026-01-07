import json
import uuid

from services.orchestrator.main import envelope, process_message
from core.schema_registry import load_registry
from core.config import Settings
from core.backlog_store import BacklogStore
from core.question_store import QuestionStore


class DummySettings(Settings):
    stream_name: str = "audit:events"


def _env(event_type: str, payload: dict):
    return envelope(
        event_type=event_type,
        payload=payload,
        source="test",
        correlation_id=str(uuid.uuid4()),
        causation_id=None,
    )


def test_human_approval_flags(redis_client):
    reg = load_registry("schemas")
    settings = DummySettings()
    store = BacklogStore(redis_client)
    qstore = QuestionStore(redis_client)
    from core.redis_streams import ensure_consumer_group
    ensure_consumer_group(redis_client, settings.stream_name, settings.consumer_group)

    pending_env = _env("HUMAN.APPROVAL_REQUESTED", {"project_id": str(uuid.uuid4()), "backlog_item_id": "b1", "reason": "policy"})
    process_message(redis_client, reg, store, qstore, settings, settings.consumer_group, "1-0", {"event": json.dumps(pending_env)})
    assert redis_client.exists(f"approval:pending:{pending_env['payload']['project_id']}:b1")

    submitted_env = _env("HUMAN.APPROVAL_SUBMITTED", {"project_id": pending_env["payload"]["project_id"], "backlog_item_id": "b1", "approved": True})
    process_message(redis_client, reg, store, qstore, settings, settings.consumer_group, "2-0", {"event": json.dumps(submitted_env)})
    assert not redis_client.exists(f"approval:pending:{pending_env['payload']['project_id']}:b1")
