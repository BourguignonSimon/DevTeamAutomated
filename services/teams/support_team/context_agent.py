from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class SupportContextAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="support_context", role="context")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        context = "support_context_ready"
        shared_context.update({"support_context": context})
        return {"context": context}
