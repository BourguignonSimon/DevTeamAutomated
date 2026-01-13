from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Set

log = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class IllegalTransition(Exception):
    item_id: str | None
    from_state: BacklogStatus
    to_state: BacklogStatus
    allowed_transitions: Set[BacklogStatus]


def is_allowed(from_status: BacklogStatus, to_status: BacklogStatus) -> bool:
    from_status = _coerce_status(from_status)
    to_status = _coerce_status(to_status)
    return to_status in _ALLOWED.get(from_status, set())


def _coerce_status(status: BacklogStatus | str) -> BacklogStatus:
    if isinstance(status, BacklogStatus):
        return status
    return BacklogStatus(str(status))


def assert_transition(
    from_status: BacklogStatus | str,
    to_status: BacklogStatus | str,
    *,
    item_id: str | None = None,
) -> TransitionResult:
    from_status = _coerce_status(from_status)
    to_status = _coerce_status(to_status)
    if is_allowed(from_status, to_status):
        return TransitionResult(True, from_status, to_status, None)
    exc = IllegalTransition(
        item_id=item_id,
        from_state=from_status,
        to_state=to_status,
        allowed_transitions=_ALLOWED.get(from_status, set()),
    )
    log.error(
        "Illegal transition",
        extra={
            "item_id": item_id,
            "from_state": from_status.value,
            "to_state": to_status.value,
            "allowed": [s.value for s in _ALLOWED.get(from_status, set())],
        },
    )
    raise exc
