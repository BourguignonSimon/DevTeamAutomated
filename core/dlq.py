from __future__ import annotations

import json
import time
from typing import Dict, Any, Optional
import redis


def _try_parse_event(original_fields: Dict[str, str]) -> Dict[str, Any]:
    """Best-effort parse of the original event.

    We keep both:
      - original_fields (raw Redis stream fields)
      - original_event (decoded JSON from field 'event' when present)
    """
    raw = original_fields.get("event")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def publish_dlq(
    r: redis.Redis,
    dlq_stream: str,
    reason: str,
    original_fields: Dict[str, str],
    schema_id: Optional[str] = None,
) -> str:
    original_event = _try_parse_event(original_fields)
    doc: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_id": original_event.get("event_id"),
        "event_type": original_event.get("event_type"),
        "reason": reason,
        "schema_id": schema_id,
        "original_event": original_event or None,
        "original_fields": original_fields,
    }
    return r.xadd(dlq_stream, {"dlq": json.dumps(doc)})
