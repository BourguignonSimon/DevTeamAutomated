from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class RemediationAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="remediation_agent", role="remediation")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        classification = shared_context.get().get("classification", "unknown")
        remediation = "propose_mitigation" if classification == "risk_detected" else "no_action"
        shared_context.update({"remediation": remediation})
        return {"remediation": remediation}
