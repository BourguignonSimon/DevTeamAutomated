from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class SupportAnalyticsAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="support_analytics", role="analytics")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        metrics = "support_metrics_ready"
        shared_context.update({"support_metrics": metrics})
        return {"metrics": metrics}
