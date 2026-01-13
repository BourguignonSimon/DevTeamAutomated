from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class EditorAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="editor_agent", role="editor")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        outline = "structured_outline"
        shared_context.update({"writing_outline": outline})
        return {"outline": outline}
