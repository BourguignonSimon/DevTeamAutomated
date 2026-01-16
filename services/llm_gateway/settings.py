"""LLM Gateway Settings.

This module provides configuration for the LLM Gateway service,
supporting both environment variables and YAML configuration files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm_config import LLMConfig, load_config, get_config


@dataclass(frozen=True)
class GatewaySettings:
    """Settings for the LLM Gateway service.

    Supports configuration from:
    1. Environment variables (for backwards compatibility)
    2. YAML configuration file (preferred)

    Environment variables take precedence over YAML config.
    """
    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Provider order (comma-separated list)
    provider_order: tuple[str, ...] = field(default_factory=lambda: tuple(
        [p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "anthropic,openai,google,local").split(",") if p.strip()]
    ))

    # Timeout and retry settings
    timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "120"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

    # Cache settings
    cache_enabled: bool = os.getenv("LLM_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
    cache_ttl_s: int = int(os.getenv("LLM_CACHE_TTL_S", "3600"))

    # API keys (from environment)
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    local_llm_url: str | None = os.getenv("LOCAL_LLM_URL") or None

    # Test mode
    test_mode: bool = os.getenv("LLM_TEST_MODE", "false").lower() in {"1", "true", "yes"}

    # Configuration file path
    config_path: str | None = os.getenv("LLM_CONFIG_PATH") or None

    def __post_init__(self) -> None:
        """Validate settings after initialization."""
        # Ensure provider_order is a tuple
        if isinstance(object.__getattribute__(self, 'provider_order'), list):
            object.__setattr__(self, 'provider_order', tuple(self.provider_order))

    def get_llm_config(self) -> LLMConfig:
        """Get the full LLM configuration.

        Loads from YAML config file if available, otherwise
        returns configuration based on environment variables.

        Returns:
            LLMConfig instance
        """
        try:
            return load_config(self.config_path)
        except Exception:
            # Fall back to basic config from env vars
            return get_config()

    def get_provider_settings(self, provider_name: str) -> Dict[str, Any]:
        """Get settings for a specific provider.

        Args:
            provider_name: Name of the provider

        Returns:
            Dict with provider settings
        """
        settings: Dict[str, Any] = {
            "timeout_seconds": self.timeout_s,
            "max_retries": self.max_retries,
        }

        if provider_name == "anthropic":
            settings["api_key"] = self.anthropic_api_key
        elif provider_name == "openai":
            settings["api_key"] = self.openai_api_key
        elif provider_name == "google":
            settings["api_key"] = self.gemini_api_key
        elif provider_name == "local":
            settings["base_url"] = self.local_llm_url

        return settings

    def is_provider_available(self, provider_name: str) -> bool:
        """Check if a provider is available (has required credentials).

        Args:
            provider_name: Name of the provider

        Returns:
            True if provider is available
        """
        if self.test_mode:
            return True  # In test mode, all providers are "available"

        if provider_name == "anthropic":
            return bool(self.anthropic_api_key)
        elif provider_name == "openai":
            return bool(self.openai_api_key)
        elif provider_name == "google":
            return bool(self.gemini_api_key)
        elif provider_name == "local":
            # Local provider is available if URL is set or using default
            return True

        return False

    def get_available_providers(self) -> List[str]:
        """Get list of available providers.

        Returns:
            List of provider names that are configured and available
        """
        return [
            p for p in self.provider_order
            if self.is_provider_available(p)
        ]
