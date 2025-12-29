import json
import time
import uuid

from core.config import Settings
from core.redis_streams import build_redis_client


def make_envelope(event_type: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "service": "demo_seed",
            "instance": "demo-1",  # REQUIRED by EPIC 1
        },
        "correlation_id": str(uuid.uuid4()),
        "causation_id": None,
        "payload": payload,
    }


def main() -> int:
    s = Settings()
    r = build_redis_client(s.redis_host, s.redis_port, s.redis_db)

    envelope = make_envelope(
        "PROJECT.INITIAL_REQUEST_RECEIVED",
        {
            "project_id": str(uuid.uuid4()),
            "request_text": "Build EPIC 2 orchestrator",
            "requester": {"name": "Simon"},
            "constraints": {"language": "fr"},
        },
    )

    msg_id = r.xadd(
        s.stream_name,
        {"event": json.dumps(envelope)},
    )

    print(
        f"Seeded event_type={envelope['event_type']} "
        f"event_id={envelope['event_id']} "
        f"redis_id={msg_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
