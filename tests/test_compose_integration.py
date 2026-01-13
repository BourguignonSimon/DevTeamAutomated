import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import redis

from core.backlog_store import BacklogStore
from core.event_utils import envelope

COMPOSE_FILE = Path(__file__).resolve().parent.parent / "docker-compose.yml"


def _wait_for(predicate, timeout=30, interval=1):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _compose_up():
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "redis", "orchestrator", "validator", "worker"], check=True)


def _compose_down():
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], check=False)


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("docker"), reason="docker not available")
def test_pipeline_dispatches_and_completes(tmp_path):
    _compose_up()
    try:
        r = redis.Redis(host="localhost", port=6380, decode_responses=True)
        assert _wait_for(lambda: r.ping(), timeout=20)

        project_id = str(uuid.uuid4())
        env = envelope(
            event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
            source="tests",
            payload={"project_id": project_id, "request_text": "perform full audit of all systems"},
            correlation_id=str(uuid.uuid4()),
            causation_id=None,
        )
        r.xadd("audit:events", {"event": json.dumps(env)})

        store = BacklogStore(r)

        def has_completion():
            for _mid, fields in r.xrevrange("audit:events", count=50):
                env_raw = fields.get("event")
                if not env_raw:
                    continue
                data = json.loads(env_raw)
                if data.get("event_type") == "WORK.ITEM_COMPLETED" and data.get("payload", {}).get("project_id") == project_id:
                    return True
            return False

        assert _wait_for(has_completion, timeout=40, interval=2)

        # ensure backlog moved out of READY
        project_ids = store.list_project_ids()
        assert project_id in project_ids
        item_ids = store.list_item_ids(project_id)
        assert item_ids
        statuses = {store.get_item(project_id, iid)["status"] for iid in item_ids}
        assert "DONE" in statuses or "IN_PROGRESS" in statuses
    finally:
        _compose_down()


@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("docker"), reason="docker not available")
def test_invalid_event_routed_to_dlq(tmp_path):
    _compose_up()
    try:
        r = redis.Redis(host="localhost", port=6380, decode_responses=True)
        assert _wait_for(lambda: r.ping(), timeout=20)

        before = r.xlen("audit:dlq")
        r.xadd("audit:events", {"event": json.dumps({"event_type": "UNKNOWN", "event_version": 1})})
        assert _wait_for(lambda: r.xlen("audit:dlq") > before, timeout=20, interval=2)
    finally:
        _compose_down()
