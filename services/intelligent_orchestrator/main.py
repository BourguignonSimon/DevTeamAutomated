from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from core.agent_team import AgentTeam, SharedContext, TeamPlan, TeamResult
from core.shared_memory import SharedMemory

log = logging.getLogger("intelligent_orchestrator")


@dataclass
class OrchestrationPhase:
    team_id: str
    objective: str


@dataclass
class OrchestrationPlan:
    project_id: str
    phases: List[OrchestrationPhase]


class IntelligentOrchestrator:
    def __init__(self, teams: Dict[str, AgentTeam], memory: SharedMemory | None = None) -> None:
        self.teams = teams
        self.memory = memory or SharedMemory()

    def analyze_request(self, project_id: str, request: str) -> OrchestrationPlan:
        lowered = request.lower()
        phases: List[OrchestrationPhase] = []

        if any(keyword in lowered for keyword in ["analyse", "analysis", "diagnostic", "risque", "risk"]):
            phases.append(OrchestrationPhase(team_id="analysis_team", objective="Analyze the request"))
        if any(keyword in lowered for keyword in ["email", "courriel", "mail"]):
            phases.append(OrchestrationPhase(team_id="email_team", objective="Draft email output"))
        if any(keyword in lowered for keyword in ["admin", "administratif", "task"]):
            phases.append(OrchestrationPhase(team_id="admin_team", objective="Handle admin actions"))
        if any(keyword in lowered for keyword in ["rédaction", "writing", "editor", "style"]):
            phases.append(OrchestrationPhase(team_id="writing_team", objective="Prepare written narrative"))
        if any(keyword in lowered for keyword in ["support", "help", "assistance"]):
            phases.append(OrchestrationPhase(team_id="support_team", objective="Provide support output"))

        if not phases:
            phases.append(OrchestrationPhase(team_id="analysis_team", objective="Default analysis"))

        return OrchestrationPlan(project_id=project_id, phases=phases)

    def coordinate(self, project_id: str, request: str) -> Dict[str, TeamResult]:
        plan = self.analyze_request(project_id, request)
        shared_context = SharedContext(project_id=project_id, memory=self.memory)
        shared_context.add_conversation({"role": "user", "content": request})
        shared_context.set_state({"status": "in_progress", "phases": [phase.team_id for phase in plan.phases]})

        results: Dict[str, TeamResult] = {}
        for phase in plan.phases:
            team = self.teams.get(phase.team_id)
            if not team:
                log.warning("team not found: %s", phase.team_id)
                continue
            shared_context.add_decision({"team": phase.team_id, "objective": phase.objective})
            team_plan: TeamPlan = team.build_plan(request, shared_context)
            results[phase.team_id] = team.run_plan(team_plan, shared_context)

        shared_context.set_state({"status": "complete", "team_count": len(results)})
        return results

    def synthesize(self, results: Dict[str, TeamResult]) -> str:
        if not results:
            return "No team results available."
        summaries = [result.summary for result in results.values()]
        return " | ".join(summaries)
