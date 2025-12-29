from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

import redis


class BacklogStore:
    """Redis-backed store for BacklogItems.

    Storage:
      - item doc:  audit:project:{project_id}:backlog:item:{item_id}
      - index all: audit:project:{project_id}:backlog:index
      - index by status: audit:project:{project_id}:backlog:status:{STATUS}
    """

    def __init__(self, r: redis.Redis, prefix: str = "audit"):
        self.r = r
        self.prefix = prefix

    def _key(self, project_id: str, item_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:backlog:item:{item_id}"

    def _index(self, project_id: str) -> str:
        return f"{self.prefix}:project:{project_id}:backlog:index"

    def _status_index(self, project_id: str, status: str) -> str:
        return f"{self.prefix}:project:{project_id}:backlog:status:{status}"

    @staticmethod
    def _decode(v) -> str:
        if isinstance(v, bytes):
            return v.decode("utf-8")
        return str(v)

    def put_item(self, item: Dict[str, Any]) -> None:
        """Upsert an item and maintain indexes."""
        project_id = item["project_id"]
        item_id = item["id"]

        prev = self.get_item(project_id, item_id)
        prev_status = prev.get("status") if prev else None
        new_status = item.get("status")

        self.r.set(self._key(project_id, item_id), json.dumps(item))
        self.r.sadd(self._index(project_id), item_id)

        if prev_status and prev_status != new_status:
            self.r.srem(self._status_index(project_id, prev_status), item_id)
        if new_status:
            self.r.sadd(self._status_index(project_id, new_status), item_id)

    def set_status(self, project_id: str, item_id: str, new_status: str) -> None:
        item = self.get_item(project_id, item_id)
        if not item:
            raise KeyError(f"unknown backlog_item_id {item_id}")
        if item.get("status") == new_status:
            return
        item["status"] = new_status
        self.put_item(item)

    def get_item(self, project_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        raw = self.r.get(self._key(project_id, item_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def list_item_ids(self, project_id: str) -> List[str]:
        ids = [self._decode(x) for x in self.r.smembers(self._index(project_id))]
        return sorted(ids)

    def list_item_ids_by_status(self, project_id: str, status: str) -> List[str]:
        ids = [self._decode(x) for x in self.r.smembers(self._status_index(project_id, status))]
        return sorted(ids)

    def iter_items(self, project_id: str) -> Iterable[Dict[str, Any]]:
        for item_id in self.list_item_ids(project_id):
            it = self.get_item(project_id, item_id)
            if it:
                yield it

    def iter_items_by_status(self, project_id: str, status: str) -> Iterable[Dict[str, Any]]:
        for item_id in self.list_item_ids_by_status(project_id, status):
            it = self.get_item(project_id, item_id)
            if it:
                yield it
