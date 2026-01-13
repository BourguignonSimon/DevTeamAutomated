from __future__ import annotations

from typing import Dict

from core.agent_team import SharedContext, TeamMember, TeamTask


class StyleKeeperAgent(TeamMember):
    def __init__(self) -> None:
        super().__init__(name="style_keeper", role="style")

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, str]:
        style = "consistent_tone"
        shared_context.update({"writing_style": style})
        return {"style": style}
