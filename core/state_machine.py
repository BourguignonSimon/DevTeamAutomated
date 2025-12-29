from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set


class BacklogStatus(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    BLOCKED = "BLOCKED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"


_ALLOWED: Dict[BacklogStatus, Set[BacklogStatus]] = {
    BacklogStatus.CREATED: {BacklogStatus.READY, BacklogStatus.BLOCKED},
    BacklogStatus.READY: {BacklogStatus.IN_PROGRESS, BacklogStatus.BLOCKED},
    BacklogStatus.BLOCKED: {BacklogStatus.READY},
    BacklogStatus.IN_PROGRESS: {BacklogStatus.DONE, BacklogStatus.FAILED, BacklogStatus.BLOCKED},
    BacklogStatus.DONE: set(),
    BacklogStatus.FAILED: set(),
}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    from_status: BacklogStatus
    to_status: BacklogStatus
    reason: str | None = None


def is_allowed(from_status: BacklogStatus, to_status: BacklogStatus) -> bool:
    return to_status in _ALLOWED.get(from_status, set())


def assert_transition(from_status: BacklogStatus, to_status: BacklogStatus) -> TransitionResult:
    if is_allowed(from_status, to_status):
        return TransitionResult(True, from_status, to_status, None)
    return TransitionResult(False, from_status, to_status, f"Illegal transition {from_status} -> {to_status}")
