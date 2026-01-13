from __future__ import annotations

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamTask
from services.teams.admin_team.classifier_agent import AdminClassifierAgent
from services.teams.admin_team.executor_agent import AdminExecutorAgent


class AdminTeam(AgentTeam):
    def __init__(self) -> None:
        members = [AdminClassifierAgent(), AdminExecutorAgent()]
        super().__init__(team_id="admin_team", members=members)

    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        tasks = [
            TeamTask(name="classify", description="Classify admin task urgency", payload={"text": request}),
            TeamTask(name="execute", description="Execute admin task", payload={}),
        ]
        return TeamPlan(team_id=self.team_id, tasks=tasks, strategy="sequential")
