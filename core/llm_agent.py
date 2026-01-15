"""Base LLM-Powered Agent Class.

This module provides a base class for creating AI agents that use LLM capabilities
from multiple providers (Anthropic, OpenAI, Google, Local).
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.llm_config import (
    AgentLLMConfig,
    LLMConfigurationManager,
    get_llm_config,
)
from services.llm_gateway.providers import (
    AnthropicProvider,
    GeminiProvider,
    GenerationConfig,
    GenerationResult,
    LocalProvider,
    Message,
    OpenAIProvider,
    Provider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)

log = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Context information passed to the agent for processing."""
    project_id: str
    backlog_item_id: str
    work_context: Dict[str, Any]
    correlation_id: str
    event_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Response from an LLM-powered agent."""
    success: bool
    content: str
    structured_output: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[TokenUsage] = None
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: float = 0.0
    error: Optional[str] = None


class LLMAgent(ABC):
    """Base class for LLM-powered agents in the processing layer.

    This class provides:
    - Multi-provider LLM support (Anthropic, OpenAI, Google, Local)
    - Configuration-based provider/model selection
    - Automatic fallback between providers
    - Tool/function calling support
    - Conversation history management
    - Retry logic with exponential backoff

    Subclasses should implement:
    - agent_name: Property returning the agent's name
    - build_system_prompt(): Method to build the system prompt
    - process(): Method to process work items using LLM
    """

    def __init__(
        self,
        config_manager: Optional[LLMConfigurationManager] = None,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
    ):
        """Initialize the LLM Agent.

        Args:
            config_manager: Optional config manager. Uses global if not provided.
            provider_override: Override the configured provider
            model_override: Override the configured model
        """
        self._config_manager = config_manager or get_llm_config()
        self._provider_override = provider_override
        self._model_override = model_override
        self._providers: Dict[str, Provider] = {}
        self._conversation_history: List[Message] = []
        self._total_tokens_used = TokenUsage()

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return the agent's name for configuration lookup."""
        raise NotImplementedError

    def get_config(self) -> AgentLLMConfig:
        """Get the LLM configuration for this agent."""
        return self._config_manager.get_agent_config_or_default(self.agent_name)

    def get_provider(self, provider_name: Optional[str] = None) -> Provider:
        """Get or create a provider instance.

        Args:
            provider_name: Optional provider name. Uses config if not provided.

        Returns:
            Provider instance
        """
        name = provider_name or self._provider_override or self.get_config().provider

        if name in self._providers:
            return self._providers[name]

        provider_config = self._config_manager.get_provider(name)
        api_key = self._config_manager.get_api_key(name)

        if name == "anthropic":
            provider = AnthropicProvider(
                api_key=api_key,
                api_base_url=provider_config.api_base_url if provider_config else "https://api.anthropic.com",
                api_version=provider_config.api_version if provider_config else "2023-06-01",
            )
        elif name == "openai":
            provider = OpenAIProvider(
                api_key=api_key,
                api_base_url=provider_config.api_base_url if provider_config else "https://api.openai.com/v1/chat/completions",
            )
        elif name == "google":
            provider = GeminiProvider(
                api_key=api_key,
                api_base_url=provider_config.api_base_url if provider_config else "https://generativelanguage.googleapis.com/v1beta/models",
            )
        elif name == "local":
            provider = LocalProvider(
                api_base_url=provider_config.api_base_url if provider_config else "http://localhost:11434/v1/chat/completions",
            )
        else:
            raise ValueError(f"Unknown provider: {name}")

        self._providers[name] = provider
        return provider

    @abstractmethod
    def build_system_prompt(self, context: AgentContext) -> str:
        """Build the system prompt for the LLM.

        Args:
            context: The agent context with work details

        Returns:
            System prompt string
        """
        raise NotImplementedError

    def get_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Return the tools/functions available to this agent.

        Override this method to provide tools for function calling.

        Returns:
            List of tool definitions, or None if no tools
        """
        return None

    def generate(
        self,
        messages: List[Message],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt override
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            tools: Optional tools for function calling
            tool_choice: Optional tool choice mode
            response_format: Optional response format (for JSON mode)

        Returns:
            GenerationResult with the LLM's response

        Raises:
            ProviderError: If all providers fail
        """
        config = self.get_config()
        fallback = self._config_manager.fallback_config

        # Build generation config
        model = self._model_override or config.model
        gen_config = GenerationConfig(
            model=model,
            temperature=temperature if temperature is not None else config.temperature,
            max_tokens=max_tokens if max_tokens is not None else config.max_tokens,
            system_prompt=system_prompt or config.system_prompt,
            tools=tools or self.get_tools(),
            tool_choice=tool_choice,
            response_format=response_format,
            stop_sequences=list(config.stop_sequences) if config.stop_sequences else [],
        )

        # Determine provider order
        if fallback.enabled:
            provider_order = list(fallback.provider_order)
            # Move configured provider to front
            primary = self._provider_override or config.provider
            if primary in provider_order:
                provider_order.remove(primary)
            provider_order.insert(0, primary)
        else:
            provider_order = [self._provider_override or config.provider]

        last_error: Optional[Exception] = None

        for provider_name in provider_order:
            try:
                provider = self.get_provider(provider_name)

                # Retry logic
                for attempt in range(fallback.max_retries + 1):
                    try:
                        result = provider.generate(messages, gen_config)

                        # Track token usage
                        self._total_tokens_used = TokenUsage(
                            input_tokens=self._total_tokens_used.input_tokens + result.usage.input_tokens,
                            output_tokens=self._total_tokens_used.output_tokens + result.usage.output_tokens,
                            total_tokens=self._total_tokens_used.total_tokens + result.usage.total_tokens,
                        )

                        log.debug(
                            f"LLM generation successful: provider={provider_name}, "
                            f"model={result.model}, tokens={result.usage.total_tokens}"
                        )
                        return result

                    except RateLimitError as e:
                        wait_time = e.retry_after or (fallback.retry_backoff ** attempt)
                        log.warning(f"Rate limit hit, waiting {wait_time}s")
                        time.sleep(wait_time)
                        continue

                    except ProviderError as e:
                        if not e.retryable:
                            raise
                        wait_time = fallback.retry_backoff ** attempt
                        log.warning(f"Provider error (attempt {attempt + 1}): {e}, waiting {wait_time}s")
                        time.sleep(wait_time)
                        continue

            except Exception as e:
                last_error = e
                log.warning(f"Provider {provider_name} failed: {e}")
                continue

        raise ProviderError(
            f"All providers failed. Last error: {last_error}",
            retryable=False
        )

    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        include_history: bool = True,
    ) -> AgentResponse:
        """Have a conversation turn with the LLM.

        Args:
            user_message: The user's message
            system_prompt: Optional system prompt
            include_history: Whether to include conversation history

        Returns:
            AgentResponse with the result
        """
        # Build messages
        messages = []
        if include_history:
            messages.extend(self._conversation_history)

        messages.append(Message(role="user", content=user_message))

        try:
            result = self.generate(messages, system_prompt=system_prompt)

            # Update conversation history
            self._conversation_history.append(Message(role="user", content=user_message))
            self._conversation_history.append(Message(role="assistant", content=result.content))

            # Parse structured output if JSON
            structured = None
            try:
                structured = json.loads(result.content)
            except (json.JSONDecodeError, TypeError):
                pass

            return AgentResponse(
                success=True,
                content=result.content,
                structured_output=structured,
                tool_calls=result.tool_calls,
                usage=result.usage,
                provider_used=self._provider_override or self.get_config().provider,
                model_used=result.model,
                latency_ms=result.latency_ms,
            )

        except Exception as e:
            log.error(f"Chat failed: {e}")
            return AgentResponse(
                success=False,
                content="",
                error=str(e),
            )

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """Execute a tool and return the result.

        Override this method to implement tool execution.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result as string
        """
        return json.dumps({"error": f"Tool {tool_name} not implemented"})

    def run_with_tools(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        max_tool_calls: int = 10,
    ) -> AgentResponse:
        """Run a conversation with automatic tool execution.

        This method will:
        1. Send the user message to the LLM
        2. If the LLM requests tool calls, execute them
        3. Send tool results back to the LLM
        4. Repeat until no more tool calls or max reached

        Args:
            user_message: The user's message
            system_prompt: Optional system prompt
            max_tool_calls: Maximum number of tool call iterations

        Returns:
            Final AgentResponse
        """
        messages = list(self._conversation_history)
        messages.append(Message(role="user", content=user_message))

        tools = self.get_tools()
        if not tools:
            return self.chat(user_message, system_prompt)

        total_usage = TokenUsage()
        tool_iterations = 0

        while tool_iterations < max_tool_calls:
            result = self.generate(
                messages,
                system_prompt=system_prompt,
                tools=tools,
                tool_choice="auto",
            )

            total_usage = TokenUsage(
                input_tokens=total_usage.input_tokens + result.usage.input_tokens,
                output_tokens=total_usage.output_tokens + result.usage.output_tokens,
                total_tokens=total_usage.total_tokens + result.usage.total_tokens,
            )

            # Add assistant message
            messages.append(Message(
                role="assistant",
                content=result.content,
                tool_calls=result.tool_calls,
            ))

            # Check if we need to execute tools
            if not result.tool_calls:
                # No more tool calls, return final response
                self._conversation_history = messages
                return AgentResponse(
                    success=True,
                    content=result.content,
                    usage=total_usage,
                    provider_used=self._provider_override or self.get_config().provider,
                    model_used=result.model,
                    latency_ms=result.latency_ms,
                )

            # Execute each tool call
            for tool_call in result.tool_calls:
                func = tool_call.get("function", {})
                tool_name = func.get("name", "")
                try:
                    arguments = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    arguments = {}

                log.debug(f"Executing tool: {tool_name} with args: {arguments}")

                try:
                    tool_result = self.execute_tool(tool_name, arguments)
                except Exception as e:
                    tool_result = json.dumps({"error": str(e)})

                # Add tool result message
                messages.append(Message(
                    role="user",
                    content=tool_result,
                    tool_call_id=tool_call.get("id"),
                    name=tool_name,
                ))

            tool_iterations += 1

        # Max iterations reached
        return AgentResponse(
            success=True,
            content=messages[-1].content if messages else "",
            usage=total_usage,
            error=f"Max tool iterations ({max_tool_calls}) reached",
        )

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._conversation_history = []

    def get_token_usage(self) -> TokenUsage:
        """Get total token usage across all generations."""
        return self._total_tokens_used

    @abstractmethod
    def process(self, context: AgentContext) -> AgentResponse:
        """Process a work item using LLM capabilities.

        This is the main method that subclasses should implement
        to define their specific behavior.

        Args:
            context: The agent context with work details

        Returns:
            AgentResponse with the processing result
        """
        raise NotImplementedError


class SimpleAnalysisAgent(LLMAgent):
    """A simple analysis agent that processes work items with LLM.

    This is a concrete implementation example that can be used
    as a template for more specific agents.
    """

    def __init__(
        self,
        name: str = "analysis_agent",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._name = name

    @property
    def agent_name(self) -> str:
        return self._name

    def build_system_prompt(self, context: AgentContext) -> str:
        return f"""You are an AI analysis agent working on project {context.project_id}.
Your task is to analyze the provided work context and generate insights.

Respond with a JSON object containing:
- "summary": Brief summary of the analysis
- "insights": List of key insights
- "recommendations": List of recommendations
- "confidence": Confidence score from 0.0 to 1.0
"""

    def process(self, context: AgentContext) -> AgentResponse:
        """Process the work context and generate analysis."""
        system_prompt = self.build_system_prompt(context)

        # Format work context for the LLM
        work_data = json.dumps(context.work_context, indent=2)
        user_message = f"Please analyze the following work context:\n\n{work_data}"

        response = self.chat(
            user_message=user_message,
            system_prompt=system_prompt,
        )

        return response
