from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class TraceRecord:
    agent: str
    event_type: str
    decision: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    correlation_id: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class TraceLogger:
    def __init__(self, redis_client=None, prefix: str = "audit:trace"):
        self.redis = redis_client
        self.prefix = prefix

    def log(self, record: TraceRecord) -> None:
        key = f"{self.prefix}:{record.agent}"
        payload = record.to_json()
        if self.redis is not None and hasattr(self.redis, "xadd"):
            self.redis.xadd(key, {"trace": payload})
        else:
            # fallback for in-memory tests: store as list on self
            store = getattr(self, "_store", {})
            store.setdefault(key, []).append(payload)
            self._store = store

    def fetch(self, agent: str) -> list[Dict[str, Any]]:
        key = f"{self.prefix}:{agent}"
        if self.redis is not None and hasattr(self.redis, "xrange"):
            return [json.loads(fields.get("trace", "{}")) for _, fields in self.redis.xrange(key, count=100)]
        store = getattr(self, "_store", {})
        return [json.loads(p) for p in store.get(key, [])]
