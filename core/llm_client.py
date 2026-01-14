"""Unified LLM Client for Agents.

This module provides a unified interface for agents to interact with
multiple LLM providers. It handles provider selection, fallback,
configuration loading, and error handling automatically.

Usage:
    from core.llm_client import LLMClient

    # Create client with default configuration
    client = LLMClient()

    # Make a prediction
    result = client.predict(
        prompt={"query": "What is machine learning?"},
        agent_name="my_agent",
    )

    # Or use the convenience function
    from core.llm_client import predict
    result = predict("What is machine learning?")
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from core.llm_config import (
    LLMConfig,
    ProviderConfig,
    get_config,
    load_config,
)

log = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers.

    This client provides:
    - Automatic provider selection based on agent/task configuration
    - Fallback to alternative providers on failure
    - Configuration-driven model selection
    - Consistent API across all providers
    - Usage tracking and cost estimation

    Attributes:
        config: LLM configuration instance
        providers: Dictionary of initialized provider instances
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        config_path: Optional[str] = None,
    ) -> None:
        """Initialize the LLM client.

        Args:
            config: Optional LLMConfig instance. If not provided,
                   loads from default configuration.
            config_path: Optional path to configuration file.
        """
        if config:
            self.config = config
        elif config_path:
            self.config = load_config(config_path)
        else:
            self.config = get_config()

        self._providers: Dict[str, Any] = {}
        self._usage_stats: Dict[str, Dict[str, Any]] = {}

    def _get_provider(self, provider_name: str) -> Any:
        """Get or create a provider instance.

        Args:
            provider_name: Name of the provider

        Returns:
            Provider instance

        Raises:
            ValueError: If provider is not configured or disabled
        """
        if provider_name in self._providers:
            return self._providers[provider_name]

        provider_config = self.config.get_provider_config(provider_name)
        if not provider_config:
            raise ValueError(f"Provider '{provider_name}' is not configured")

        if not provider_config.enabled:
            raise ValueError(f"Provider '{provider_name}' is disabled")

        # Import and instantiate provider based on name
        provider = self._create_provider(provider_name, provider_config)
        self._providers[provider_name] = provider
        return provider

    def _create_provider(self, name: str, config: ProviderConfig) -> Any:
        """Create a provider instance from configuration.

        Args:
            name: Provider name
            config: Provider configuration

        Returns:
            Provider instance
        """
        timeout = config.settings.get("timeout_seconds", self.config.timeout_seconds)
        max_retries = config.settings.get("max_retries", self.config.max_retries)

        if name == "anthropic":
            from services.llm_gateway.providers.anthropic import AnthropicProvider
            return AnthropicProvider(
                api_key=config.api_key,
                base_url=config.base_url,
                api_version=config.api_version,
                default_model=config.default_model,
                timeout_seconds=timeout,
                max_retries=max_retries,
            )
        elif name == "openai":
            from services.llm_gateway.providers.openai import OpenAIProvider
            return OpenAIProvider(
                api_key=config.api_key,
                base_url=config.base_url,
                organization_id=config.organization_id,
                default_model=config.default_model,
                timeout_seconds=timeout,
                max_retries=max_retries,
            )
        elif name == "google":
            from services.llm_gateway.providers.gemini import GeminiProvider
            return GeminiProvider(
                api_key=config.api_key,
                base_url=config.base_url,
                default_model=config.default_model,
                timeout_seconds=timeout,
                max_retries=max_retries,
                safety_settings=config.safety_settings,
            )
        elif name == "local":
            from services.llm_gateway.providers.local import LocalProvider
            return LocalProvider(
                server_type=config.server_type or "ollama",
                base_url=config.base_url,
                api_key=config.api_key,
                default_model=config.default_model,
                timeout_seconds=timeout,
                max_retries=max_retries,
            )
        else:
            raise ValueError(f"Unknown provider: {name}")

    def predict(
        self,
        prompt: Union[str, Dict[str, Any]],
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        fallback: bool = True,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the configured LLM provider.

        Args:
            prompt: The prompt as a string or dict with structured data
            agent_name: Name of the calling agent (for config lookup)
            task_type: Type of task (for config lookup)
            provider: Override provider (bypasses config lookup)
            model: Override model (bypasses config lookup)
            temperature: Override temperature
            max_tokens: Override max tokens
            system_prompt: System prompt for context
            tools: Tool definitions for function calling
            fallback: Whether to fallback to other providers on failure

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            RuntimeError: If all providers fail
        """
        # Get effective configuration
        effective_config = self.config.get_effective_config(
            agent_name=agent_name,
            task_type=task_type,
        )

        # Apply overrides
        if provider:
            effective_config["provider"] = provider
        if model:
            effective_config["model"] = model
        if temperature is not None:
            effective_config["temperature"] = temperature
        if max_tokens is not None:
            effective_config["max_tokens"] = max_tokens

        # Convert string prompt to dict
        if isinstance(prompt, str):
            prompt = {"prompt": prompt}

        # Determine provider order for fallback
        if fallback:
            provider_order = [effective_config["provider"]]
            for p in self.config.fallback_order:
                if p != effective_config["provider"] and p not in provider_order:
                    provider_order.append(p)
        else:
            provider_order = [effective_config["provider"]]

        last_error: Optional[Exception] = None
        errors: List[str] = []

        for provider_name in provider_order:
            try:
                provider_config = self.config.get_provider_config(provider_name)
                if not provider_config or not provider_config.enabled:
                    continue

                provider_instance = self._get_provider(provider_name)

                # Determine model to use
                use_model = effective_config["model"]
                if provider_name != effective_config["provider"]:
                    # Using fallback provider, use its default model
                    use_model = provider_config.default_model

                log.info(f"Making prediction with {provider_name}/{use_model}")

                result, usage = provider_instance.predict(
                    prompt=prompt,
                    model=use_model,
                    max_tokens=effective_config["max_tokens"],
                    temperature=effective_config["temperature"],
                    system_prompt=system_prompt,
                    tools=tools,
                )

                # Track usage
                self._track_usage(provider_name, usage, agent_name, task_type)

                return result, usage

            except Exception as e:
                last_error = e
                error_msg = f"{provider_name}: {str(e)}"
                errors.append(error_msg)
                log.warning(f"Provider {provider_name} failed: {e}")

                if not fallback:
                    break

                # Wait before trying next provider
                time.sleep(self.config.retry_base_delay_seconds)

        # All providers failed
        error_summary = "; ".join(errors)
        raise RuntimeError(f"All providers failed: {error_summary}")

    async def predict_async(
        self,
        prompt: Union[str, Dict[str, Any]],
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        fallback: bool = True,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Async version of predict method.

        Args:
            prompt: The prompt as a string or dict with structured data
            agent_name: Name of the calling agent (for config lookup)
            task_type: Type of task (for config lookup)
            provider: Override provider (bypasses config lookup)
            model: Override model (bypasses config lookup)
            temperature: Override temperature
            max_tokens: Override max tokens
            system_prompt: System prompt for context
            tools: Tool definitions for function calling
            fallback: Whether to fallback to other providers on failure

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            RuntimeError: If all providers fail
        """
        import asyncio

        # Get effective configuration
        effective_config = self.config.get_effective_config(
            agent_name=agent_name,
            task_type=task_type,
        )

        # Apply overrides
        if provider:
            effective_config["provider"] = provider
        if model:
            effective_config["model"] = model
        if temperature is not None:
            effective_config["temperature"] = temperature
        if max_tokens is not None:
            effective_config["max_tokens"] = max_tokens

        # Convert string prompt to dict
        if isinstance(prompt, str):
            prompt = {"prompt": prompt}

        # Determine provider order for fallback
        if fallback:
            provider_order = [effective_config["provider"]]
            for p in self.config.fallback_order:
                if p != effective_config["provider"] and p not in provider_order:
                    provider_order.append(p)
        else:
            provider_order = [effective_config["provider"]]

        last_error: Optional[Exception] = None
        errors: List[str] = []

        for provider_name in provider_order:
            try:
                provider_config = self.config.get_provider_config(provider_name)
                if not provider_config or not provider_config.enabled:
                    continue

                provider_instance = self._get_provider(provider_name)

                # Determine model to use
                use_model = effective_config["model"]
                if provider_name != effective_config["provider"]:
                    use_model = provider_config.default_model

                log.info(f"Making async prediction with {provider_name}/{use_model}")

                result, usage = await provider_instance.predict_async(
                    prompt=prompt,
                    model=use_model,
                    max_tokens=effective_config["max_tokens"],
                    temperature=effective_config["temperature"],
                    system_prompt=system_prompt,
                    tools=tools,
                )

                # Track usage
                self._track_usage(provider_name, usage, agent_name, task_type)

                return result, usage

            except Exception as e:
                last_error = e
                error_msg = f"{provider_name}: {str(e)}"
                errors.append(error_msg)
                log.warning(f"Provider {provider_name} failed: {e}")

                if not fallback:
                    break

                # Wait before trying next provider
                await asyncio.sleep(self.config.retry_base_delay_seconds)

        # All providers failed
        error_summary = "; ".join(errors)
        raise RuntimeError(f"All providers failed: {error_summary}")

    def stream(
        self,
        prompt: Union[str, Dict[str, Any]],
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ):
        """Stream responses from the LLM provider.

        Args:
            prompt: The prompt as a string or dict
            agent_name: Name of the calling agent
            task_type: Type of task
            provider: Override provider
            model: Override model
            temperature: Override temperature
            max_tokens: Override max tokens
            system_prompt: System prompt for context

        Yields:
            Partial response dicts
        """
        # Get effective configuration
        effective_config = self.config.get_effective_config(
            agent_name=agent_name,
            task_type=task_type,
        )

        # Apply overrides
        if provider:
            effective_config["provider"] = provider
        if model:
            effective_config["model"] = model
        if temperature is not None:
            effective_config["temperature"] = temperature
        if max_tokens is not None:
            effective_config["max_tokens"] = max_tokens

        # Convert string prompt to dict
        if isinstance(prompt, str):
            prompt = {"prompt": prompt}

        provider_name = effective_config["provider"]
        provider_instance = self._get_provider(provider_name)

        log.info(f"Starting stream with {provider_name}/{effective_config['model']}")

        yield from provider_instance.stream(
            prompt=prompt,
            model=effective_config["model"],
            max_tokens=effective_config["max_tokens"],
            temperature=effective_config["temperature"],
            system_prompt=system_prompt,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Send a chat conversation to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            agent_name: Name of the calling agent
            task_type: Type of task
            provider: Override provider
            model: Override model
            temperature: Override temperature
            max_tokens: Override max tokens
            system_prompt: System prompt for context
            tools: Tool definitions for function calling

        Returns:
            Tuple of (result_dict, usage_dict)
        """
        prompt = {
            "messages": messages,
        }
        if system_prompt:
            prompt["system_prompt"] = system_prompt

        return self.predict(
            prompt=prompt,
            agent_name=agent_name,
            task_type=task_type,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=None,  # Already in prompt
            tools=tools,
        )

    def _track_usage(
        self,
        provider: str,
        usage: Dict[str, Any],
        agent_name: Optional[str],
        task_type: Optional[str],
    ) -> None:
        """Track usage statistics for cost monitoring.

        Args:
            provider: Provider name
            usage: Usage dictionary from provider
            agent_name: Name of the agent
            task_type: Type of task
        """
        if not self.config.cost_tracking.enabled:
            return

        # Initialize provider stats if needed
        if provider not in self._usage_stats:
            self._usage_stats[provider] = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_requests": 0,
                "by_agent": {},
                "by_task_type": {},
            }

        stats = self._usage_stats[provider]
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        stats["total_input_tokens"] += input_tokens
        stats["total_output_tokens"] += output_tokens
        stats["total_requests"] += 1

        # Track by agent
        if agent_name and self.config.cost_tracking.track_by_agent:
            if agent_name not in stats["by_agent"]:
                stats["by_agent"][agent_name] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "requests": 0,
                }
            stats["by_agent"][agent_name]["input_tokens"] += input_tokens
            stats["by_agent"][agent_name]["output_tokens"] += output_tokens
            stats["by_agent"][agent_name]["requests"] += 1

        # Track by task type
        if task_type and self.config.cost_tracking.track_by_task_type:
            if task_type not in stats["by_task_type"]:
                stats["by_task_type"][task_type] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "requests": 0,
                }
            stats["by_task_type"][task_type]["input_tokens"] += input_tokens
            stats["by_task_type"][task_type]["output_tokens"] += output_tokens
            stats["by_task_type"][task_type]["requests"] += 1

    def get_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get current usage statistics.

        Returns:
            Dictionary of usage stats by provider
        """
        return self._usage_stats.copy()

    def estimate_cost(self, provider: Optional[str] = None) -> float:
        """Estimate total cost based on usage and model pricing.

        Args:
            provider: Optional provider to filter by

        Returns:
            Estimated cost in USD
        """
        total_cost = 0.0

        providers_to_check = [provider] if provider else list(self._usage_stats.keys())

        for prov in providers_to_check:
            if prov not in self._usage_stats:
                continue

            stats = self._usage_stats[prov]
            provider_config = self.config.get_provider_config(prov)

            if not provider_config:
                continue

            # Use default model pricing
            default_model = provider_config.default_model
            model_config = provider_config.models.get(default_model)

            if model_config:
                input_cost = (stats["total_input_tokens"] / 1000) * model_config.cost_per_1k_input_tokens
                output_cost = (stats["total_output_tokens"] / 1000) * model_config.cost_per_1k_output_tokens
                total_cost += input_cost + output_cost

        return total_cost

    def reset_usage_stats(self) -> None:
        """Reset usage statistics."""
        self._usage_stats.clear()


# Global client instance (lazy loaded)
_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    """Get the global LLM client instance.

    Returns:
        LLMClient instance
    """
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def predict(
    prompt: Union[str, Dict[str, Any]],
    agent_name: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Convenience function to make a prediction using the global client.

    Args:
        prompt: The prompt as a string or dict
        agent_name: Name of the calling agent
        task_type: Type of task
        **kwargs: Additional arguments passed to LLMClient.predict()

    Returns:
        Tuple of (result_dict, usage_dict)
    """
    return get_client().predict(
        prompt=prompt,
        agent_name=agent_name,
        task_type=task_type,
        **kwargs,
    )


async def predict_async(
    prompt: Union[str, Dict[str, Any]],
    agent_name: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Convenience function for async prediction using the global client.

    Args:
        prompt: The prompt as a string or dict
        agent_name: Name of the calling agent
        task_type: Type of task
        **kwargs: Additional arguments passed to LLMClient.predict_async()

    Returns:
        Tuple of (result_dict, usage_dict)
    """
    return await get_client().predict_async(
        prompt=prompt,
        agent_name=agent_name,
        task_type=task_type,
        **kwargs,
    )


def chat(
    messages: List[Dict[str, str]],
    agent_name: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Convenience function for chat using the global client.

    Args:
        messages: List of message dicts
        agent_name: Name of the calling agent
        task_type: Type of task
        **kwargs: Additional arguments passed to LLMClient.chat()

    Returns:
        Tuple of (result_dict, usage_dict)
    """
    return get_client().chat(
        messages=messages,
        agent_name=agent_name,
        task_type=task_type,
        **kwargs,
    )
