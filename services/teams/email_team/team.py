from __future__ import annotations

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamTask
from services.teams.email_team.parser_agent import EmailParserAgent
from services.teams.email_team.writer_agent import EmailWriterAgent


class EmailTeam(AgentTeam):
    def __init__(self) -> None:
        members = [EmailParserAgent(), EmailWriterAgent()]
        super().__init__(team_id="email_team", members=members)

    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        tasks = [
            TeamTask(name="parse", description="Parse email intent", payload={"text": request}),
            TeamTask(name="write", description="Write email draft", payload={}),
        ]
        return TeamPlan(team_id=self.team_id, tasks=tasks, strategy="sequential")
