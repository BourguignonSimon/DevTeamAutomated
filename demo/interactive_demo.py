import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from core.config import Settings
from core.redis_streams import build_redis_client


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_envelope(
    *,
    event_type: str,
    payload: Dict[str, Any],
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    service: str = "demo",
    instance: Optional[str] = None,
    event_version: int = 1,
) -> Dict[str, Any]:
    # EPIC 1 compliant envelope
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "timestamp": now_iso(),
        "source": {
            "service": service,
            "instance": instance or os.getenv("HOSTNAME", "demo-1"),
        },
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "causation_id": causation_id,
        "payload": payload,
    }


def xadd_event(r, stream: str, env: Dict[str, Any]) -> str:
    return r.xadd(stream, {"event": json.dumps(env)})


def read_latest_dlq(r, dlq_stream: str, count: int = 10):
    # XRANGE - + COUNT is simplest for demo: get last entries using XREVRANGE
    msgs = r.xrevrange(dlq_stream, max="+", min="-", count=count)
    out = []
    for msg_id, fields in msgs:
        try:
            doc = json.loads(fields.get("dlq", "{}"))
        except Exception:
            doc = {"raw": fields.get("dlq")}
        out.append((msg_id, doc))
    return out


def print_menu():
    print("\n=== Audit Flash OS Demo ===")
    print("1) Create new project (valid intake)")
    print("2) Dispatch next READY task (manual trigger event if your orchestrator expects it)")
    print("3) Simulate worker START (WORK.ITEM_STARTED)")
    print("4) Simulate worker COMPLETE with evidence (WORK.ITEM_COMPLETED)")
    print("5) Simulate worker COMPLETE without evidence (should fail -> DLQ)")
    print("6) Inject INVALID envelope (missing source.instance) -> DLQ")
    print("7) Show DLQ (last 10)")
    print("8) Show backlog keys in Redis (quick view)")
    print("9) Exit")


def pick(prompt: str) -> str:
    return input(prompt).strip()


def main() -> int:
    s = Settings()
    r = build_redis_client(s.redis_host, s.redis_port, s.redis_db)

    # Demo state
    project_id: Optional[str] = None
    correlation_id: Optional[str] = None
    last_backlog_item_id: Optional[str] = None

    print(f"Connected to redis={s.redis_host}:{s.redis_port} stream={s.stream_name} dlq={s.dlq_stream}")

    while True:
        print_menu()
        choice = pick("> ")

        try:
            if choice == "1":
                project_id = str(uuid.uuid4())
                correlation_id = str(uuid.uuid4())
                env = make_envelope(
                    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
                    payload={
                        "project_id": project_id,
                        "request_text": "Demo request: generate backlog + dispatch",
                        "requester": {"name": "Simon"},
                        "constraints": {"language": "en"},
                    },
                    correlation_id=correlation_id,
                    causation_id=None,
                    service="demo",
                )
                msg_id = xadd_event(r, s.stream_name, env)
                print(f"✅ sent intake project_id={project_id} redis_id={msg_id}")

            elif choice == "2":
                if not project_id or not correlation_id:
                    print("Create a project first (1).")
                    continue

                # Some orchestrators auto-dispatch. If yours expects a nudge event, use a custom one.
                # If not needed, skip this option.
                env = make_envelope(
                    event_type="WORK.DISPATCH_REQUESTED",
                    payload={"project_id": project_id},
                    correlation_id=correlation_id,
                    causation_id=None,
                    service="demo",
                )
                msg_id = xadd_event(r, s.stream_name, env)
                print(f"✅ sent WORK.DISPATCH_REQUESTED redis_id={msg_id}")
                print("Note: only useful if orchestrator supports this event_type.")

            elif choice == "3":
                project_id = project_id or pick("project_id: ")
                backlog_item_id = pick("backlog_item_id (task): ")
                last_backlog_item_id = backlog_item_id

                env = make_envelope(
                    event_type="WORK.ITEM_STARTED",
                    payload={"project_id": project_id, "backlog_item_id": backlog_item_id, "started_at": now_iso()},
                    correlation_id=correlation_id,
                    causation_id=None,
                    service="demo_worker",
                )
                msg_id = xadd_event(r, s.stream_name, env)
                print(f"✅ sent WORK.ITEM_STARTED redis_id={msg_id}")

            elif choice == "4":
                project_id = project_id or pick("project_id: ")
                backlog_item_id = last_backlog_item_id or pick("backlog_item_id (task): ")

                # Evidence keys should match your DoD logic. Keep it simple for demo:
                env = make_envelope(
                    event_type="WORK.ITEM_COMPLETED",
                    payload={
                        "project_id": project_id,
                        "backlog_item_id": backlog_item_id,
                        "status": "DONE",
                        "evidence": {
                            "artifact_uri": "reports/demo.md",
                            "tests_passed": True,
                            "notes": "Demo completion evidence",
                        },
                    },
                    correlation_id=correlation_id,
                    causation_id=None,
                    service="demo_worker",
                )
                msg_id = xadd_event(r, s.stream_name, env)
                print(f"✅ sent WORK.ITEM_COMPLETED (with evidence) redis_id={msg_id}")

            elif choice == "5":
                project_id = project_id or pick("project_id: ")
                backlog_item_id = last_backlog_item_id or pick("backlog_item_id (task): ")

                # No evidence => should fail schema or DoD check => DLQ
                env = make_envelope(
                    event_type="WORK.ITEM_COMPLETED",
                    payload={"project_id": project_id, "backlog_item_id": backlog_item_id, "status": "DONE"},
                    correlation_id=correlation_id,
                    causation_id=None,
                    service="demo_worker",
                )
                msg_id = xadd_event(r, s.stream_name, env)
                print(f"✅ sent WORK.ITEM_COMPLETED (missing evidence) redis_id={msg_id}")

            elif choice == "6":
                # Intentionally invalid: missing source.instance
                bad_env = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "PROJECT.INITIAL_REQUEST_RECEIVED",
                    "event_version": 1,
                    "timestamp": now_iso(),
                    "source": {"service": "bad_demo"},  # instance missing on purpose
                    "correlation_id": str(uuid.uuid4()),
                    "causation_id": None,
                    "payload": {"project_id": str(uuid.uuid4()), "request_text": "bad"},
                }
                msg_id = xadd_event(r, s.stream_name, bad_env)
                print(f"✅ sent INVALID envelope redis_id={msg_id} (should go DLQ)")

            elif choice == "7":
                dlq = read_latest_dlq(r, s.dlq_stream, 10)
                print("\n--- DLQ last 10 ---")
                for msg_id, doc in dlq:
                    print(f"* {msg_id}: {doc.get('reason')}")
                if not dlq:
                    print("(DLQ empty)")

            elif choice == "8":
                # quick “what exists”
                pattern = "audit:project:*"
                keys = r.keys(pattern)
                print(f"Keys matching {pattern}:")
                for k in sorted(keys)[:50]:
                    print(" -", k)
                if len(keys) > 50:
                    print(f"... ({len(keys)} total)")

            elif choice == "9":
                return 0

            else:
                print("Unknown option.")

        except Exception as e:
            # Demo-friendly error handling
            print(f"❌ Demo error: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
