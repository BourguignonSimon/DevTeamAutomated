from __future__ import annotations

from services.intelligent_orchestrator.main import IntelligentOrchestrator
from services.teams import AdminTeam, AnalysisTeam, EmailTeam, SupportTeam, WritingTeam


def run_demo() -> None:
    teams = {
        "analysis_team": AnalysisTeam(),
        "admin_team": AdminTeam(),
        "email_team": EmailTeam(),
        "writing_team": WritingTeam(),
        "support_team": SupportTeam(),
    }
    orchestrator = IntelligentOrchestrator(teams=teams)
    request = "Analyse ce document et rédige un email de synthèse"
    results = orchestrator.coordinate(project_id="00000000-0000-0000-0000-000000000000", request=request)
    print(orchestrator.synthesize(results))


if __name__ == "__main__":
    run_demo()
