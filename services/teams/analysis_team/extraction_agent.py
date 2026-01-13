from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class ExtractionAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="extraction_agent", role="extraction")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        text = task.payload.get("text", "")
        extracted = "key_points" if text else "no_content"
        shared_context.update({"extracted": extracted})
        return {"extracted": extracted}
