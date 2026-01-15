from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MemorySnapshot:
    context: Dict[str, Any]
    conversations: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]
    results: Dict[str, Any]
    state: Dict[str, Any]


class SharedMemory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._context: Dict[str, Dict[str, Any]] = {}
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._decisions: Dict[str, List[Dict[str, Any]]] = {}
        self._results: Dict[str, Dict[str, Any]] = {}
        self._state: Dict[str, Dict[str, Any]] = {}

    def get_context(self, project_id: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._context.get(project_id, {}))

    def update_context(self, project_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            context = self._context.setdefault(project_id, {})
            context.update(updates)
            return dict(context)

    def append_conversation(self, project_id: str, message: Dict[str, Any]) -> None:
        with self._lock:
            self._conversations.setdefault(project_id, []).append(dict(message))

    def append_decision(self, project_id: str, decision: Dict[str, Any]) -> None:
        with self._lock:
            self._decisions.setdefault(project_id, []).append(dict(decision))

    def store_result(self, project_id: str, key: str, result: Any) -> None:
        with self._lock:
            self._results.setdefault(project_id, {})[key] = result

    def set_state(self, project_id: str, state: Dict[str, Any]) -> None:
        with self._lock:
            self._state[project_id] = dict(state)

    def snapshot(self, project_id: str) -> MemorySnapshot:
        with self._lock:
            return MemorySnapshot(
                context=dict(self._context.get(project_id, {})),
                conversations=list(self._conversations.get(project_id, [])),
                decisions=list(self._decisions.get(project_id, [])),
                results=dict(self._results.get(project_id, {})),
                state=dict(self._state.get(project_id, {})),
            )
