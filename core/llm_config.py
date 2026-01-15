"""LLM Provider Configuration Loader.

This module handles loading, validating, and providing access to LLM provider
configurations for AI agents in the processing layer.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger(__name__)

# Default config path
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "llm_providers.yaml"
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "config" / "llm_config.v1.schema.json"


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a specific LLM model."""
    id: str
    name: str
    max_tokens: int = 4096
    context_window: int = 128000
    supports_tools: bool = False
    supports_vision: bool = False


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration for a provider."""
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    enabled: bool
    api_base_url: str
    api_version: Optional[str] = None
    models: tuple[ModelConfig, ...] = field(default_factory=tuple)
    rate_limits: Optional[RateLimitConfig] = None

    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """Get a model configuration by ID."""
        for model in self.models:
            if model.id == model_id:
                return model
        return None

    def get_default_model(self) -> Optional[ModelConfig]:
        """Get the first (default) model for this provider."""
        return self.models[0] if self.models else None


@dataclass(frozen=True)
class AgentLLMConfig:
    """LLM configuration for a specific agent."""
    agent_name: str
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: Optional[str] = None
    top_p: Optional[float] = None
    stop_sequences: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FallbackConfig:
    """Fallback configuration for provider failures."""
    enabled: bool = True
    provider_order: tuple[str, ...] = ("anthropic", "openai", "google", "local")
    max_retries: int = 2
    retry_backoff: float = 1.5


@dataclass(frozen=True)
class CacheConfig:
    """Caching configuration for LLM responses."""
    enabled: bool = True
    ttl_seconds: int = 3600
    max_entries: int = 1000
    include_temperature_in_key: bool = True


@dataclass(frozen=True)
class MonitoringConfig:
    """Monitoring configuration for LLM requests."""
    log_requests: bool = True
    log_responses: bool = False
    log_token_usage: bool = True
    metrics_enabled: bool = True


class LLMConfigurationManager:
    """Manager for LLM provider configurations.

    Loads configuration from YAML file, validates against schema,
    and provides access to provider and agent configurations.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path(os.getenv("LLM_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
        self._raw_config: Dict[str, Any] = {}
        self._providers: Dict[str, ProviderConfig] = {}
        self._agent_configs: Dict[str, AgentLLMConfig] = {}
        self._default_provider: str = "anthropic"
        self._default_models: Dict[str, str] = {}
        self._fallback_config: FallbackConfig = FallbackConfig()
        self._cache_config: CacheConfig = CacheConfig()
        self._monitoring_config: MonitoringConfig = MonitoringConfig()
        self._loaded = False

    def load(self) -> None:
        """Load and parse the configuration file."""
        if self._loaded:
            return

        if not self._config_path.exists():
            log.warning(f"Config file not found at {self._config_path}, using defaults")
            self._apply_defaults()
            self._loaded = True
            return

        try:
            with open(self._config_path, "r") as f:
                self._raw_config = yaml.safe_load(f) or {}

            self._validate_config()
            self._parse_config()
            self._loaded = True
            log.info(f"Loaded LLM configuration from {self._config_path}")
        except Exception as e:
            log.error(f"Failed to load LLM config: {e}")
            self._apply_defaults()
            self._loaded = True

    def _validate_config(self) -> None:
        """Validate configuration against JSON schema."""
        if not SCHEMA_PATH.exists():
            log.warning("Schema file not found, skipping validation")
            return

        try:
            from jsonschema import Draft202012Validator
            with open(SCHEMA_PATH, "r") as f:
                schema = json.load(f)
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(self._raw_config))
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    log.warning(f"Config validation error: {error.message}")
        except ImportError:
            log.debug("jsonschema not available, skipping validation")
        except Exception as e:
            log.warning(f"Config validation failed: {e}")

    def _parse_config(self) -> None:
        """Parse raw configuration into dataclasses."""
        # Default provider
        self._default_provider = self._raw_config.get("default_provider", "anthropic")
        self._default_models = self._raw_config.get("default_models", {})

        # Parse providers
        providers_raw = self._raw_config.get("providers", {})
        for name, config in providers_raw.items():
            self._providers[name] = self._parse_provider(name, config)

        # Parse agent configs
        agent_configs_raw = self._raw_config.get("agent_configs", {})
        for agent_name, config in agent_configs_raw.items():
            self._agent_configs[agent_name] = self._parse_agent_config(agent_name, config)

        # Parse fallback config
        fallback_raw = self._raw_config.get("fallback", {})
        self._fallback_config = FallbackConfig(
            enabled=fallback_raw.get("enabled", True),
            provider_order=tuple(fallback_raw.get("provider_order", ["anthropic", "openai", "google", "local"])),
            max_retries=fallback_raw.get("max_retries", 2),
            retry_backoff=fallback_raw.get("retry_backoff", 1.5),
        )

        # Parse cache config
        cache_raw = self._raw_config.get("cache", {})
        self._cache_config = CacheConfig(
            enabled=cache_raw.get("enabled", True),
            ttl_seconds=cache_raw.get("ttl_seconds", 3600),
            max_entries=cache_raw.get("max_entries", 1000),
            include_temperature_in_key=cache_raw.get("include_temperature_in_key", True),
        )

        # Parse monitoring config
        monitoring_raw = self._raw_config.get("monitoring", {})
        self._monitoring_config = MonitoringConfig(
            log_requests=monitoring_raw.get("log_requests", True),
            log_responses=monitoring_raw.get("log_responses", False),
            log_token_usage=monitoring_raw.get("log_token_usage", True),
            metrics_enabled=monitoring_raw.get("metrics_enabled", True),
        )

    def _parse_provider(self, name: str, config: Dict[str, Any]) -> ProviderConfig:
        """Parse a provider configuration."""
        models = []
        for model_raw in config.get("models", []):
            models.append(ModelConfig(
                id=model_raw["id"],
                name=model_raw["name"],
                max_tokens=model_raw.get("max_tokens", 4096),
                context_window=model_raw.get("context_window", 128000),
                supports_tools=model_raw.get("supports_tools", False),
                supports_vision=model_raw.get("supports_vision", False),
            ))

        rate_limits = None
        if "rate_limits" in config:
            rl = config["rate_limits"]
            rate_limits = RateLimitConfig(
                requests_per_minute=rl.get("requests_per_minute", 60),
                tokens_per_minute=rl.get("tokens_per_minute", 100000),
            )

        return ProviderConfig(
            name=name,
            enabled=config.get("enabled", False),
            api_base_url=config.get("api_base_url", ""),
            api_version=config.get("api_version"),
            models=tuple(models),
            rate_limits=rate_limits,
        )

    def _parse_agent_config(self, agent_name: str, config: Dict[str, Any]) -> AgentLLMConfig:
        """Parse an agent LLM configuration."""
        return AgentLLMConfig(
            agent_name=agent_name,
            provider=config["provider"],
            model=config["model"],
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 4096),
            system_prompt=config.get("system_prompt"),
            top_p=config.get("top_p"),
            stop_sequences=tuple(config.get("stop_sequences", [])),
        )

    def _apply_defaults(self) -> None:
        """Apply default configuration when no config file exists."""
        self._default_provider = "anthropic"
        self._default_models = {
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "google": "gemini-2.0-flash",
            "local": "llama3.2:latest",
        }

        # Minimal default providers
        self._providers = {
            "anthropic": ProviderConfig(
                name="anthropic",
                enabled=True,
                api_base_url="https://api.anthropic.com",
                api_version="2023-06-01",
                models=(ModelConfig(id="claude-sonnet-4-20250514", name="Claude Sonnet 4"),),
            ),
            "openai": ProviderConfig(
                name="openai",
                enabled=True,
                api_base_url="https://api.openai.com/v1",
                models=(ModelConfig(id="gpt-4o", name="GPT-4o"),),
            ),
            "google": ProviderConfig(
                name="google",
                enabled=True,
                api_base_url="https://generativelanguage.googleapis.com/v1beta",
                models=(ModelConfig(id="gemini-2.0-flash", name="Gemini 2.0 Flash"),),
            ),
            "local": ProviderConfig(
                name="local",
                enabled=True,
                api_base_url="http://localhost:11434",
                models=(ModelConfig(id="llama3.2:latest", name="Llama 3.2"),),
            ),
        }

    @property
    def default_provider(self) -> str:
        """Get the default provider name."""
        self.load()
        return self._default_provider

    def get_default_model(self, provider: str) -> Optional[str]:
        """Get the default model for a provider."""
        self.load()
        return self._default_models.get(provider)

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Get a provider configuration by name."""
        self.load()
        return self._providers.get(name)

    def get_enabled_providers(self) -> List[ProviderConfig]:
        """Get all enabled providers."""
        self.load()
        return [p for p in self._providers.values() if p.enabled]

    def get_agent_config(self, agent_name: str) -> Optional[AgentLLMConfig]:
        """Get LLM configuration for a specific agent."""
        self.load()
        return self._agent_configs.get(agent_name)

    def get_agent_config_or_default(self, agent_name: str) -> AgentLLMConfig:
        """Get agent config or create default from global settings."""
        self.load()
        config = self._agent_configs.get(agent_name)
        if config:
            return config

        # Return default configuration
        return AgentLLMConfig(
            agent_name=agent_name,
            provider=self._default_provider,
            model=self._default_models.get(self._default_provider, "claude-sonnet-4-20250514"),
            temperature=0.7,
            max_tokens=4096,
        )

    @property
    def fallback_config(self) -> FallbackConfig:
        """Get fallback configuration."""
        self.load()
        return self._fallback_config

    @property
    def cache_config(self) -> CacheConfig:
        """Get cache configuration."""
        self.load()
        return self._cache_config

    @property
    def monitoring_config(self) -> MonitoringConfig:
        """Get monitoring configuration."""
        self.load()
        return self._monitoring_config

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider from environment variables."""
        key_mappings = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            "local": None,  # Local providers typically don't need API keys
        }

        env_var = key_mappings.get(provider)
        if env_var is None:
            return None

        if isinstance(env_var, list):
            for var in env_var:
                key = os.getenv(var)
                if key:
                    return key
            return None

        return os.getenv(env_var)


# Global singleton instance
_config_manager: Optional[LLMConfigurationManager] = None


def get_llm_config() -> LLMConfigurationManager:
    """Get the global LLM configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = LLMConfigurationManager()
    return _config_manager


def reset_llm_config() -> None:
    """Reset the global configuration manager (for testing)."""
    global _config_manager
    _config_manager = None
