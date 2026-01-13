from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class EmailParserAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="email_parser", role="parser")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        intent = "summary" if "summary" in task.description.lower() else "general"
        shared_context.update({"email_intent": intent})
        return {"intent": intent}
