from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class EmailWriterAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="email_writer", role="writer")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        intent = shared_context.get().get("email_intent", "general")
        draft = f"email_draft_for_{intent}"
        shared_context.update({"email_draft": draft})
        return {"draft": draft}
