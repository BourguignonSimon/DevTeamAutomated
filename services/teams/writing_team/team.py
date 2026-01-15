from __future__ import annotations

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamTask
from services.teams.writing_team.editor_agent import EditorAgent
from services.teams.writing_team.style_keeper_agent import StyleKeeperAgent


class WritingTeam(AgentTeam):
    def __init__(self) -> None:
        members = [EditorAgent(), StyleKeeperAgent()]
        super().__init__(team_id="writing_team", members=members)

    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        tasks = [
            TeamTask(name="outline", description="Create outline", payload={"text": request}),
            TeamTask(name="polish", description="Apply style rules", payload={}),
        ]
        return TeamPlan(team_id=self.team_id, tasks=tasks, strategy="sequential")
