from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import redis

from core.config import Settings
from core.phase_runner import run_with_timeout

log = logging.getLogger("agent_manager")


class Phase(str, Enum):
    ANALYZE = "analyse"
    ARCHITECTURE = "architecture"
    CODE = "code"
    REVIEW = "review"


@dataclass
class PhaseState:
    phase: Phase
    message_id: str
    timestamp: float


class StateJournal:
    """Persist minimal state to allow resuming after restarts.

    Depending on how the manager is wired, we persist both locally and in Redis
    so that an operator can pick up the last known phase + message id even if
    the container filesystem is ephemeral.
    """

    def __init__(
        self,
        *,
        redis_client: Optional[redis.Redis] = None,
        redis_hash_key: str = "agent_manager:state",
        journal_path: str | Path = ".agent_manager_journal.jsonl",
    ) -> None:
        self.redis_client = redis_client
        self.redis_hash_key = redis_hash_key
        self.journal_path = Path(journal_path)

    def record(self, state: PhaseState) -> None:
        entry = {
            "phase": state.phase.value,
            "message_id": state.message_id,
            "timestamp": state.timestamp,
        }
        try:
            if self.redis_client is not None:
                self.redis_client.hset(self.redis_hash_key, mapping=entry)
        except Exception as exc:  # best effort persistence
            log.warning("Unable to persist state to redis: %s", exc)

        try:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:
            log.warning("Unable to persist state locally: %s", exc)

    def clear(self) -> None:
        try:
            if self.redis_client is not None:
                self.redis_client.delete(self.redis_hash_key)
        except Exception as exc:
            log.warning("Unable to clear redis journal state: %s", exc)
        try:
            if self.journal_path.exists():
                self.journal_path.unlink()
        except Exception as exc:
            log.warning("Unable to clear local journal state: %s", exc)

    def last_known_state(self) -> Optional[PhaseState]:
        state: Optional[PhaseState] = None
        try:
            if self.redis_client is not None and self.redis_client.exists(self.redis_hash_key):
                data = self.redis_client.hgetall(self.redis_hash_key)
                phase = data.get("phase")
                message_id = data.get("message_id")
                timestamp = float(data.get("timestamp", 0))
                if phase and message_id:
                    state = PhaseState(Phase(phase), message_id, timestamp)
        except Exception:
            state = None

        if state is not None:
            return state

        if not self.journal_path.exists():
            return None

        try:
            with self.journal_path.open("r", encoding="utf-8") as fh:
                lines = [ln.strip() for ln in fh.readlines() if ln.strip()]
            if not lines:
                return None
            data = json.loads(lines[-1])
            return PhaseState(Phase(data["phase"]), data["message_id"], float(data.get("timestamp", 0)))
        except Exception:
            return None


class AgentManager:
    def __init__(
        self,
        *,
        redis_client: Optional[redis.Redis],
        settings: Settings,
        republish_handler: Optional[Callable[[str, Phase], None]] = None,
        incident_handler: Optional[Callable[[str, Phase, str], None]] = None,
        journal: Optional[StateJournal] = None,
    ) -> None:
        self.redis = redis_client
        self.settings = settings
        self.republish_handler = republish_handler
        self.incident_handler = incident_handler
        self.journal = journal or StateJournal(redis_client=redis_client)

    def _timeout_for_phase(self, phase: Phase) -> int:
        mapping: Dict[Phase, int] = {
            Phase.ANALYZE: self.settings.analyze_timeout_s,
            Phase.ARCHITECTURE: self.settings.architecture_timeout_s,
            Phase.CODE: self.settings.code_timeout_s,
            Phase.REVIEW: self.settings.review_timeout_s,
        }
        return mapping[phase]

    def _execute_with_timeout(self, func: Callable[[], None], timeout_s: int) -> Tuple[bool, Optional[str]]:
        ok, reason = run_with_timeout(func, timeout_s)
        return ok, reason

    def _persist_phase(self, phase: Phase, message_id: str) -> None:
        self.journal.record(PhaseState(phase=phase, message_id=message_id, timestamp=time.time()))

    def _handle_failure(self, phase: Phase, message_id: str, reason: str) -> None:
        if reason == "timeout" and self.republish_handler is not None:
            log.warning("Phase %s timed out for %s, republishing", phase.value, message_id)
            try:
                self.republish_handler(message_id, phase)
                return
            except Exception as exc:
                log.error("Republish handler failed for %s/%s: %s", message_id, phase.value, exc)

        log.error("Entering incident mode for %s/%s: %s", message_id, phase.value, reason)
        if self.incident_handler is not None:
            try:
                self.incident_handler(message_id, phase, reason)
            except Exception as exc:
                log.error("Incident handler failed for %s/%s: %s", message_id, phase.value, exc)

    def _run_phase(self, phase: Phase, func: Callable[[], None], message_id: str) -> bool:
        self._persist_phase(phase, message_id)
        timeout_s = self._timeout_for_phase(phase)
        ok, reason = self._execute_with_timeout(func, timeout_s)
        if ok:
            return True
        self._handle_failure(phase, message_id, reason or "unknown error")
        return False

    def _run_review_with_retry(self, func: Callable[[], None], message_id: str) -> bool:
        attempt = 0
        max_attempts = max(1, self.settings.review_max_retries)
        while attempt < max_attempts:
            attempt += 1
            if self._run_phase(Phase.REVIEW, func, message_id):
                return True
            log.warning("Retrying review for %s (attempt %s/%s)", message_id, attempt, max_attempts)
        self._handle_failure(Phase.REVIEW, message_id, "all review attempts failed")
        return False

    def run_workflow(self, message_id: str, phases: Dict[Phase, Callable[[], None]]) -> bool:
        ordered_phases = [Phase.ANALYZE, Phase.ARCHITECTURE, Phase.CODE, Phase.REVIEW]
        for phase in ordered_phases:
            handler = phases.get(phase)
            if handler is None:
                continue
            if phase == Phase.REVIEW:
                if not self._run_review_with_retry(handler, message_id):
                    return False
            else:
                if not self._run_phase(phase, handler, message_id):
                    return False
        self.journal.clear()
        return True

