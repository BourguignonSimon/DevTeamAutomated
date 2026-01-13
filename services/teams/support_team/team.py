from __future__ import annotations

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamTask
from services.teams.support_team.analytics_agent import SupportAnalyticsAgent
from services.teams.support_team.answer_agent import SupportAnswerAgent
from services.teams.support_team.context_agent import SupportContextAgent


class SupportTeam(AgentTeam):
    def __init__(self) -> None:
        members = [SupportContextAgent(), SupportAnswerAgent(), SupportAnalyticsAgent()]
        super().__init__(team_id="support_team", members=members)

    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        tasks = [
            TeamTask(name="context", description="Gather support context", payload={"text": request}),
            TeamTask(name="answer", description="Prepare support response", payload={}),
            TeamTask(name="analytics", description="Capture analytics", payload={}),
        ]
        return TeamPlan(team_id=self.team_id, tasks=tasks, strategy="sequential")
