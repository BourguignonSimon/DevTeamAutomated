from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class ClassifierAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="classifier_agent", role="classification")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        extracted = shared_context.get().get("extracted", "unknown")
        classification = "risk_detected" if extracted != "no_content" else "no_risk"
        shared_context.update({"classification": classification})
        return {"classification": classification}
