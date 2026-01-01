from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis


class OrderStore:
    def __init__(self, r: redis.Redis, *, prefix: str = "audit:orders", storage_dir: str = "/storage") -> None:
        self.r = r
        self.prefix = prefix
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_key(self, artifact_id: str) -> str:
        return f"{self.prefix}:artifact:{artifact_id}"

    def _draft_key(self, order_id: str) -> str:
        return f"{self.prefix}:{order_id}:draft"

    def _missing_key(self, order_id: str) -> str:
        return f"{self.prefix}:{order_id}:missing"

    def _anomaly_key(self, order_id: str) -> str:
        return f"{self.prefix}:{order_id}:anomalies"

    def _export_key(self, order_id: str) -> str:
        return f"{self.prefix}:{order_id}:export"

    def save_artifact_metadata(self, artifact_id: str, metadata: Dict[str, Any], ttl_s: int) -> None:
        self.r.set(self._artifact_key(artifact_id), json.dumps(metadata), ex=ttl_s)

    def get_artifact_metadata(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        raw = self.r.get(self._artifact_key(artifact_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def save_order_draft(self, order_id: str, draft: Dict[str, Any]) -> None:
        self.r.set(self._draft_key(order_id), json.dumps(draft))

    def get_order_draft(self, order_id: str) -> Optional[Dict[str, Any]]:
        raw = self.r.get(self._draft_key(order_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def save_missing_fields(self, order_id: str, missing: List[Dict[str, Any]]) -> None:
        self.r.set(self._missing_key(order_id), json.dumps(missing))

    def save_anomalies(self, order_id: str, anomalies: List[Dict[str, Any]]) -> None:
        self.r.set(self._anomaly_key(order_id), json.dumps(anomalies))

    def get_missing_fields(self, order_id: str) -> List[Dict[str, Any]]:
        raw = self.r.get(self._missing_key(order_id))
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def get_anomalies(self, order_id: str) -> List[Dict[str, Any]]:
        raw = self.r.get(self._anomaly_key(order_id))
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def record_export(self, order_id: str, export_meta: Dict[str, Any]) -> None:
        self.r.set(self._export_key(order_id), json.dumps(export_meta))

    def get_export(self, order_id: str) -> Optional[Dict[str, Any]]:
        raw = self.r.get(self._export_key(order_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def add_pending_validation(self, validation_set_key: str, order_id: str) -> None:
        self.r.sadd(validation_set_key, order_id)

    def remove_pending_validation(self, validation_set_key: str, order_id: str) -> None:
        self.r.srem(validation_set_key, order_id)

    def list_pending_validation(self, validation_set_key: str) -> List[str]:
        return sorted([oid if isinstance(oid, str) else oid.decode("utf-8") for oid in self.r.smembers(validation_set_key)])

    def artifact_path(self, order_id: str, artifact_id: str, filename: str) -> Path:
        base = self.storage_dir / "artifacts" / order_id
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{artifact_id}_{filename}"

    def export_path(self, order_id: str) -> Path:
        base = self.storage_dir / "exports"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{order_id}.csv"
