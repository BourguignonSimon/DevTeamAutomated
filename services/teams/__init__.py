"""Team registry for multi-agent orchestration."""

from services.teams.admin_team import AdminTeam
from services.teams.analysis_team import AnalysisTeam
from services.teams.email_team import EmailTeam
from services.teams.support_team import SupportTeam
from services.teams.writing_team import WritingTeam

__all__ = [
    "AdminTeam",
    "AnalysisTeam",
    "EmailTeam",
    "SupportTeam",
    "WritingTeam",
]
