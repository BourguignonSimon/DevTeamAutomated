from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class ReportAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="report_agent", role="report")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        context = shared_context.get()
        summary = "report_ready"
        shared_context.update({"report": summary})
        return {"summary": summary, "context": context}
