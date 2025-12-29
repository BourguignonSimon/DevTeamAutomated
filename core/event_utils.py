from __future__ import annotations

import os
import time
import uuid
from typing import Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_event_id() -> str:
    return str(uuid.uuid4())


def envelope(
    *,
    event_type: str,
    payload: dict,
    source: str,
    event_version: int = 1,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    instance: Optional[str] = None,
) -> dict:
    """Build an EPIC-1 compliant EventEnvelope.

    - source: logical service name (ex: orchestrator, demo_worker)
    - instance: running instance id (defaults to HOSTNAME or <source>-1)
    - correlation_id: auto-generated if omitted
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": event_version,
        "timestamp": now_iso(),
        "source": {
            "service": source,
            "instance": instance or os.getenv("HOSTNAME", f"{source}-1"),
        },
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "causation_id": causation_id,
        "payload": payload,
    }
