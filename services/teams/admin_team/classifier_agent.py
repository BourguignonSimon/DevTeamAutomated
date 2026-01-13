from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class AdminClassifierAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="admin_classifier", role="classifier")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        priority = "high" if "urgent" in task.description.lower() else "normal"
        shared_context.update({"admin_priority": priority})
        return {"priority": priority}
