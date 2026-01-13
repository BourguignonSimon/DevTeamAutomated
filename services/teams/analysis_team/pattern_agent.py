from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class PatternAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="pattern_agent", role="pattern")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        text = task.payload.get("text", "")
        pattern = "contract" if "contract" in text.lower() else "general_document"
        shared_context.update({"document_pattern": pattern})
        return {"pattern": pattern}
