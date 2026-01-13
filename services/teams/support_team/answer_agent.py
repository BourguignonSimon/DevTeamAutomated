from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class SupportAnswerAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="support_answer", role="answer")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        response = "support_answer_prepared"
        shared_context.update({"support_answer": response})
        return {"answer": response}
