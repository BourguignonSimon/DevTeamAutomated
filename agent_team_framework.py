"""Compatibility module for the multi-agent framework exports."""

from core.agent_team import (
    AgentTeam,
    SharedContext,
    TeamCoordinator,
    TeamMember,
    TeamPlan,
    TeamResult,
    TeamTask,
)
from core.shared_memory import SharedMemory

__all__ = [
    "AgentTeam",
    "SharedContext",
    "TeamCoordinator",
    "TeamMember",
    "TeamPlan",
    "TeamResult",
    "TeamTask",
    "SharedMemory",
]
