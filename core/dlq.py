from __future__ import annotations

import json
import time
import traceback
from typing import Any, Dict, Optional

import redis

_DEF_MAX_TRACE = 4000


def _try_parse_event(original_fields: Dict[str, str]) -> Dict[str, Any]:
    """Best-effort parse of the original event."""
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
    *,
    schema_id: Optional[str] = None,
    error: Optional[BaseException] = None,
    consumer_group: Optional[str] = None,
    attempts: Optional[int] = None,
    first_seen_at: Optional[float] = None,
    last_seen_at: Optional[float] = None,
) -> str:
    original_event = _try_parse_event(original_fields)
    doc: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_id": original_event.get("event_id"),
        "event_type": original_event.get("event_type"),
        "reason": reason,
        "schema_id": schema_id,
        "consumer_group": consumer_group,
        "attempts": attempts,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "error_class": error.__class__.__name__ if error else None,
        "error_message": str(error) if error else None,
        "stack_trace": None,
        "original_event": original_event or None,
        "original_fields": original_fields,
    }
    if error:
        doc["stack_trace"] = "".join(traceback.format_exception(error))[-_DEF_MAX_TRACE:]
    return r.xadd(dlq_stream, {"dlq": json.dumps(doc)})
