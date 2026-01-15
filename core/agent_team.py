from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.collaboration_patterns import sequential_pipeline
from core.shared_memory import SharedMemory

log = logging.getLogger(__name__)


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


class AIAgent(TeamMember):
    """Base class for AI-powered agents that use LLM providers.

    This class extends TeamMember to add LLM integration capabilities.
    Agents can use multiple LLM providers (Anthropic, OpenAI, Google, Local)
    through a unified interface with automatic fallback and configuration.

    Attributes:
        name: Agent identifier used for configuration lookup
        role: Agent's role within the team
        system_prompt: Default system prompt for this agent
        task_type: Default task type for configuration lookup
        llm_client: Lazy-loaded LLM client instance
    """

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> None:
        """Initialize the AI agent.

        Args:
            name: Agent identifier (used for config lookup in agent_overrides)
            role: Agent's role within the team
            system_prompt: Default system prompt for LLM interactions
            task_type: Default task type for config lookup in task_type_overrides
        """
        super().__init__(name, role)
        self.system_prompt = system_prompt
        self.task_type = task_type
        self._llm_client = None

    @property
    def llm_client(self):
        """Lazy-load the LLM client."""
        if self._llm_client is None:
            from core.llm_client import LLMClient
            self._llm_client = LLMClient()
        return self._llm_client

    def predict(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the configured LLM provider.

        The agent's configuration is looked up from llm_config.yaml based on
        the agent name (agent_overrides section) and task type (task_type_overrides).

        Args:
            prompt: The prompt to send to the LLM
            system_prompt: Override the agent's default system prompt
            task_type: Override the agent's default task type
            temperature: Override the temperature setting
            max_tokens: Override max tokens setting
            tools: Tool definitions for function calling
            provider: Override the provider (bypasses config lookup)
            model: Override the model (bypasses config lookup)

        Returns:
            Tuple of (result_dict, usage_dict) where result_dict contains
            the LLM response and usage_dict contains token usage statistics.
        """
        effective_system_prompt = system_prompt or self.system_prompt
        effective_task_type = task_type or self.task_type

        log.info(f"Agent '{self.name}' making prediction (task_type={effective_task_type})")

        return self.llm_client.predict(
            prompt=prompt,
            agent_name=self.name,
            task_type=effective_task_type,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            provider=provider,
            model=model,
        )

    async def predict_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Async version of predict method.

        Args:
            prompt: The prompt to send to the LLM
            system_prompt: Override the agent's default system prompt
            task_type: Override the agent's default task type
            temperature: Override the temperature setting
            max_tokens: Override max tokens setting
            tools: Tool definitions for function calling
            provider: Override the provider (bypasses config lookup)
            model: Override the model (bypasses config lookup)

        Returns:
            Tuple of (result_dict, usage_dict)
        """
        effective_system_prompt = system_prompt or self.system_prompt
        effective_task_type = task_type or self.task_type

        log.info(f"Agent '{self.name}' making async prediction (task_type={effective_task_type})")

        return await self.llm_client.predict_async(
            prompt=prompt,
            agent_name=self.name,
            task_type=effective_task_type,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            provider=provider,
            model=model,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Send a chat conversation to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Override the agent's default system prompt
            task_type: Override the agent's default task type
            temperature: Override the temperature setting
            max_tokens: Override max tokens setting
            tools: Tool definitions for function calling

        Returns:
            Tuple of (result_dict, usage_dict)
        """
        effective_system_prompt = system_prompt or self.system_prompt
        effective_task_type = task_type or self.task_type

        return self.llm_client.chat(
            messages=messages,
            agent_name=self.name,
            task_type=effective_task_type,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream responses from the LLM.

        Args:
            prompt: The prompt to send to the LLM
            system_prompt: Override the agent's default system prompt
            task_type: Override the agent's default task type
            temperature: Override the temperature setting
            max_tokens: Override max tokens setting

        Yields:
            Partial response dicts as they arrive
        """
        effective_system_prompt = system_prompt or self.system_prompt
        effective_task_type = task_type or self.task_type

        yield from self.llm_client.stream(
            prompt=prompt,
            agent_name=self.name,
            task_type=effective_task_type,
            system_prompt=effective_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def get_llm_config(self) -> Dict[str, Any]:
        """Get the effective LLM configuration for this agent.

        Returns:
            Dictionary with provider, model, temperature, and max_tokens
        """
        return self.llm_client.config.get_effective_config(
            agent_name=self.name,
            task_type=self.task_type,
        )

    @abstractmethod
    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Execute a task using LLM capabilities.

        Subclasses must implement this method to define how the agent
        processes tasks using LLM predictions.

        Args:
            task: The task to execute
            shared_context: Shared context for team collaboration

        Returns:
            Dictionary containing the execution results
        """
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
