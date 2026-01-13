from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from core.collaboration_patterns import sequential_pipeline
from core.shared_memory import SharedMemory


@dataclass
class TeamTask:
    name: str
    description: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamPlan:
    team_id: str
    tasks: List[TeamTask]
    strategy: str = "sequential"
    plan_id: str | None = None


@dataclass
class TeamResult:
    team_id: str
    summary: str
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedContext:
    project_id: str
    memory: SharedMemory

    def get(self) -> Dict[str, Any]:
        return self.memory.get_context(self.project_id)

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self.memory.update_context(self.project_id, updates)

    def add_conversation(self, message: Dict[str, Any]) -> None:
        self.memory.append_conversation(self.project_id, message)

    def add_decision(self, decision: Dict[str, Any]) -> None:
        self.memory.append_decision(self.project_id, decision)

    def store_result(self, key: str, result: Any) -> None:
        self.memory.store_result(self.project_id, key, result)

    def set_state(self, state: Dict[str, Any]) -> None:
        self.memory.set_state(self.project_id, state)


class TeamMember(ABC):
    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role

    @abstractmethod
    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        raise NotImplementedError


class TeamCoordinator:
    def __init__(self, pattern: str = "sequential") -> None:
        self.pattern = pattern

    def coordinate(
        self,
        plan: TeamPlan,
        members: Iterable[TeamMember],
        shared_context: SharedContext,
    ) -> List[Dict[str, Any]]:
        if self.pattern == "sequential":
            return sequential_pipeline(list(members), plan.tasks, shared_context)
        return sequential_pipeline(list(members), plan.tasks, shared_context)


class AgentTeam(ABC):
    def __init__(self, team_id: str, members: List[TeamMember], coordinator: TeamCoordinator | None = None) -> None:
        self.team_id = team_id
        self.members = members
        self.coordinator = coordinator or TeamCoordinator()

    @abstractmethod
    def build_plan(self, request: str, shared_context: SharedContext) -> TeamPlan:
        raise NotImplementedError

    def run_plan(self, plan: TeamPlan, shared_context: SharedContext) -> TeamResult:
        results = self.coordinator.coordinate(plan, self.members, shared_context)
        summary = f"{self.team_id} completed {len(results)} steps"
        return TeamResult(team_id=self.team_id, summary=summary, details={"steps": results})
