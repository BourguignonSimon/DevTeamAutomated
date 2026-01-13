from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class AdminExecutorAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="admin_executor", role="executor")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        priority = shared_context.get().get("admin_priority", "normal")
        outcome = "queued" if priority == "normal" else "expedited"
        shared_context.update({"admin_outcome": outcome})
        return {"outcome": outcome}
