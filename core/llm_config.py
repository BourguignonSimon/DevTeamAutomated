"""LLM Configuration Loader.

This module provides configuration loading and management for the
multi-provider LLM system. It loads settings from YAML configuration
files and environment variables, supporting provider-specific and
agent-specific configurations.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger(__name__)

# Default configuration file paths
DEFAULT_CONFIG_PATHS = [
    "/app/config/llm_config.yaml",
    "./config/llm_config.yaml",
    "../config/llm_config.yaml",
    "llm_config.yaml",
]


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    name: str
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_vision: bool = False
    supports_tools: bool = False
    context_window: int = 8192
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    enabled: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str = ""
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)

    # Provider-specific fields
    api_version: Optional[str] = None
    organization_id: Optional[str] = None
    server_type: Optional[str] = None
    safety_settings: Optional[Dict[str, str]] = None


@dataclass
class AgentConfig:
    """Configuration override for a specific agent."""
    agent_name: str
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class TaskTypeConfig:
    """Configuration override for a specific task type."""
    task_type: str
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for a provider."""
    provider: str
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000


@dataclass
class CostTrackingConfig:
    """Cost tracking configuration."""
    enabled: bool = True
    daily_budget: float = 100.0
    monthly_budget: float = 2000.0
    alert_at_percentage: int = 80
    track_by_agent: bool = True
    track_by_task_type: bool = True
    track_by_project: bool = True


@dataclass
class LLMConfig:
    """Complete LLM configuration."""
    # Global settings
    default_provider: str = "anthropic"
    fallback_order: List[str] = field(default_factory=lambda: ["anthropic", "openai", "google", "local"])
    timeout_seconds: float = 120
    max_retries: int = 3
    retry_base_delay_seconds: float = 1
    retry_max_delay_seconds: float = 30
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    logging_enabled: bool = True
    log_level: str = "INFO"

    # Provider configurations
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)

    # Override configurations
    agent_overrides: Dict[str, AgentConfig] = field(default_factory=dict)
    task_type_overrides: Dict[str, TaskTypeConfig] = field(default_factory=dict)

    # Rate limiting
    rate_limiting_enabled: bool = True
    rate_limits: Dict[str, RateLimitConfig] = field(default_factory=dict)

    # Cost tracking
    cost_tracking: CostTrackingConfig = field(default_factory=CostTrackingConfig)

    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider."""
        return self.providers.get(provider_name)

    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """Get configuration override for a specific agent."""
        return self.agent_overrides.get(agent_name)

    def get_task_type_config(self, task_type: str) -> Optional[TaskTypeConfig]:
        """Get configuration override for a specific task type."""
        return self.task_type_overrides.get(task_type)

    def get_effective_config(
        self,
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get effective configuration considering overrides.

        Priority (highest to lowest):
        1. Agent-specific override
        2. Task-type override
        3. Global default

        Args:
            agent_name: Name of the agent
            task_type: Type of task

        Returns:
            Dict with effective provider, model, temperature, max_tokens
        """
        # Start with defaults
        config = {
            "provider": self.default_provider,
            "model": None,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        # Get default model from provider
        provider_config = self.providers.get(self.default_provider)
        if provider_config:
            config["model"] = provider_config.default_model

        # Apply task type override
        if task_type:
            task_config = self.task_type_overrides.get(task_type)
            if task_config:
                if task_config.provider:
                    config["provider"] = task_config.provider
                if task_config.model:
                    config["model"] = task_config.model
                if task_config.temperature is not None:
                    config["temperature"] = task_config.temperature
                if task_config.max_tokens is not None:
                    config["max_tokens"] = task_config.max_tokens

        # Apply agent override (highest priority)
        if agent_name:
            agent_config = self.agent_overrides.get(agent_name)
            if agent_config:
                if agent_config.provider:
                    config["provider"] = agent_config.provider
                if agent_config.model:
                    config["model"] = agent_config.model
                if agent_config.temperature is not None:
                    config["temperature"] = agent_config.temperature
                if agent_config.max_tokens is not None:
                    config["max_tokens"] = agent_config.max_tokens

        # Ensure model is set from provider default if not overridden
        if not config["model"]:
            provider_config = self.providers.get(config["provider"])
            if provider_config:
                config["model"] = provider_config.default_model

        return config


def _expand_env_vars(value: Any) -> Any:
    """Expand environment variables in configuration values.

    Supports ${VAR} and ${VAR:-default} syntax.
    """
    if isinstance(value, str):
        # Match ${VAR} or ${VAR:-default}
        pattern = r'\$\{([^}:]+)(?::-([^}]*))?\}'

        def replacer(match):
            var_name = match.group(1)
            default_value = match.group(2) or ""
            return os.getenv(var_name, default_value)

        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def _parse_model_config(name: str, config: Dict[str, Any]) -> ModelConfig:
    """Parse model configuration from dict."""
    return ModelConfig(
        name=name,
        max_tokens=config.get("max_tokens", 4096),
        temperature=config.get("temperature", 0.7),
        supports_vision=config.get("supports_vision", False),
        supports_tools=config.get("supports_tools", False),
        context_window=config.get("context_window", 8192),
        cost_per_1k_input_tokens=config.get("cost_per_1k_input_tokens", 0.0),
        cost_per_1k_output_tokens=config.get("cost_per_1k_output_tokens", 0.0),
    )


def _parse_provider_config(name: str, config: Dict[str, Any]) -> ProviderConfig:
    """Parse provider configuration from dict."""
    # Expand environment variables
    config = _expand_env_vars(config)

    # Parse models
    models = {}
    for model_name, model_config in config.get("models", {}).items():
        models[model_name] = _parse_model_config(model_name, model_config)

    return ProviderConfig(
        name=name,
        enabled=config.get("enabled", True),
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        default_model=config.get("default_model", ""),
        models=models,
        settings=config.get("settings", {}),
        api_version=config.get("api_version"),
        organization_id=config.get("organization_id"),
        server_type=config.get("server_type"),
        safety_settings=config.get("safety_settings"),
    )


def _parse_agent_config(name: str, config: Dict[str, Any]) -> AgentConfig:
    """Parse agent configuration from dict."""
    return AgentConfig(
        agent_name=name,
        provider=config.get("provider"),
        model=config.get("model"),
        temperature=config.get("temperature"),
        max_tokens=config.get("max_tokens"),
    )


def _parse_task_type_config(name: str, config: Dict[str, Any]) -> TaskTypeConfig:
    """Parse task type configuration from dict."""
    return TaskTypeConfig(
        task_type=name,
        provider=config.get("provider"),
        model=config.get("model"),
        temperature=config.get("temperature"),
        max_tokens=config.get("max_tokens"),
    )


def load_config(config_path: Optional[str] = None) -> LLMConfig:
    """Load LLM configuration from YAML file.

    Args:
        config_path: Path to configuration file. If not provided,
                    searches default locations.

    Returns:
        LLMConfig instance

    Raises:
        FileNotFoundError: If no configuration file found
        ValueError: If configuration is invalid
    """
    # Find configuration file
    if config_path:
        paths_to_try = [config_path]
    else:
        paths_to_try = DEFAULT_CONFIG_PATHS

        # Also check environment variable
        env_path = os.getenv("LLM_CONFIG_PATH")
        if env_path:
            paths_to_try.insert(0, env_path)

    config_file = None
    for path in paths_to_try:
        if Path(path).exists():
            config_file = path
            break

    if not config_file:
        log.warning("No LLM configuration file found, using defaults")
        return LLMConfig()

    log.info(f"Loading LLM configuration from: {config_file}")

    try:
        with open(config_file, "r") as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse configuration file: {e}")

    if not raw_config:
        return LLMConfig()

    # Expand environment variables
    raw_config = _expand_env_vars(raw_config)

    # Parse global settings
    global_config = raw_config.get("global", {})

    # Parse providers
    providers = {}
    for provider_name, provider_config in raw_config.get("providers", {}).items():
        providers[provider_name] = _parse_provider_config(provider_name, provider_config)

    # Parse agent overrides
    agent_overrides = {}
    for agent_name, agent_config in raw_config.get("agent_overrides", {}).items():
        agent_overrides[agent_name] = _parse_agent_config(agent_name, agent_config)

    # Parse task type overrides
    task_type_overrides = {}
    for task_type, task_config in raw_config.get("task_type_overrides", {}).items():
        task_type_overrides[task_type] = _parse_task_type_config(task_type, task_config)

    # Parse rate limiting
    rate_limits = {}
    rate_limiting_config = raw_config.get("rate_limiting", {})
    rate_limiting_enabled = rate_limiting_config.get("enabled", True)
    for provider_name, limit_config in rate_limiting_config.get("providers", {}).items():
        rate_limits[provider_name] = RateLimitConfig(
            provider=provider_name,
            requests_per_minute=limit_config.get("requests_per_minute", 60),
            tokens_per_minute=limit_config.get("tokens_per_minute", 100000),
        )

    # Parse cost tracking
    cost_config = raw_config.get("cost_tracking", {})
    cost_tracking = CostTrackingConfig(
        enabled=cost_config.get("enabled", True),
        daily_budget=cost_config.get("daily_budget", 100.0),
        monthly_budget=cost_config.get("monthly_budget", 2000.0),
        alert_at_percentage=cost_config.get("alert_at_percentage", 80),
        track_by_agent=cost_config.get("track_by_agent", True),
        track_by_task_type=cost_config.get("track_by_task_type", True),
        track_by_project=cost_config.get("track_by_project", True),
    )

    return LLMConfig(
        default_provider=global_config.get("default_provider", "anthropic"),
        fallback_order=global_config.get("fallback_order", ["anthropic", "openai", "google", "local"]),
        timeout_seconds=global_config.get("timeout_seconds", 120),
        max_retries=global_config.get("max_retries", 3),
        retry_base_delay_seconds=global_config.get("retry_base_delay_seconds", 1),
        retry_max_delay_seconds=global_config.get("retry_max_delay_seconds", 30),
        cache_enabled=global_config.get("cache_enabled", True),
        cache_ttl_seconds=global_config.get("cache_ttl_seconds", 3600),
        logging_enabled=global_config.get("logging_enabled", True),
        log_level=global_config.get("log_level", "INFO"),
        providers=providers,
        agent_overrides=agent_overrides,
        task_type_overrides=task_type_overrides,
        rate_limiting_enabled=rate_limiting_enabled,
        rate_limits=rate_limits,
        cost_tracking=cost_tracking,
    )


# Global configuration instance (lazy loaded)
_config: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """Get the global LLM configuration instance.

    Lazily loads configuration on first access.

    Returns:
        LLMConfig instance
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[str] = None) -> LLMConfig:
    """Reload the global LLM configuration.

    Args:
        config_path: Optional path to configuration file

    Returns:
        New LLMConfig instance
    """
    global _config
    _config = load_config(config_path)
    return _config
