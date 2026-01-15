from __future__ import annotations

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamTask
from services.teams.analysis_team.classifier_agent import ClassifierAgent
from services.teams.analysis_team.extraction_agent import ExtractionAgent
from services.teams.analysis_team.pattern_agent import PatternAgent
from services.teams.analysis_team.remediation_agent import RemediationAgent
from services.teams.analysis_team.report_agent import ReportAgent


class AnalysisTeam(AgentTeam):
    def __init__(self) -> None:
        members = [
            PatternAgent(),
            ExtractionAgent(),
            ClassifierAgent(),
            RemediationAgent(),
            ReportAgent(),
        ]
        super().__init__(team_id="analysis_team", members=members)

    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        tasks = [
            TeamTask(name="pattern", description="Identify document pattern", payload={"text": request}),
            TeamTask(name="extract", description="Extract relevant data", payload={"text": request}),
            TeamTask(name="classify", description="Classify risks", payload={}),
            TeamTask(name="remediate", description="Suggest remediation", payload={}),
            TeamTask(name="report", description="Generate report", payload={}),
        ]
        return TeamPlan(team_id=self.team_id, tasks=tasks, strategy="sequential")
