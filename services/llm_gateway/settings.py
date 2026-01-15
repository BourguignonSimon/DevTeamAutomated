"""LLM Gateway Settings.

Configuration for the LLM Gateway service.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class GatewaySettings:
    """Settings for the LLM Gateway service."""

    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Provider order for fallback
    provider_order: Tuple[str, ...] = tuple(
        [p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "anthropic,openai,google,local").split(",") if p.strip()]
    )

    # Timeout and retry settings
    timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "120"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    retry_backoff: float = float(os.getenv("LLM_RETRY_BACKOFF", "1.5"))

    # Cache settings
    cache_enabled: bool = os.getenv("LLM_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
    cache_ttl_s: int = int(os.getenv("LLM_CACHE_TTL_S", "3600"))

    # API Keys (loaded from environment)
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY") or None
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY") or None
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None

    # Local LLM settings
    local_api_url: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1/chat/completions")

    # Default models per provider
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    local_model: str = os.getenv("LOCAL_MODEL", "llama3.2:latest")

    # Test mode (uses fake provider)
    test_mode: bool = os.getenv("LLM_TEST_MODE", "false").lower() in {"1", "true", "yes"}

    # Configuration file path
    config_path: Optional[str] = os.getenv("LLM_CONFIG_PATH") or None

    def get_default_model(self, provider: str) -> str:
        """Get the default model for a provider."""
        models = {
            "anthropic": self.anthropic_model,
            "openai": self.openai_model,
            "google": self.gemini_model,
            "gemini": self.gemini_model,
            "local": self.local_model,
        }
        return models.get(provider, "")

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get the API key for a provider."""
        keys = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "google": self.gemini_api_key,
            "gemini": self.gemini_api_key,
            "local": None,
        }
        return keys.get(provider)
