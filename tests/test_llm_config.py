"""Tests for LLM configuration module."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from core.llm_config import (
    AgentLLMConfig,
    CacheConfig,
    FallbackConfig,
    LLMConfigurationManager,
    ModelConfig,
    MonitoringConfig,
    ProviderConfig,
    RateLimitConfig,
    get_llm_config,
    reset_llm_config,
)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset global config before each test."""
    reset_llm_config()
    yield
    reset_llm_config()


@pytest.fixture
def sample_config():
    """Create a sample configuration."""
    return {
        "default_provider": "anthropic",
        "default_models": {
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "google": "gemini-2.0-flash",
            "local": "llama3.2:latest",
        },
        "providers": {
            "anthropic": {
                "enabled": True,
                "api_base_url": "https://api.anthropic.com",
                "api_version": "2023-06-01",
                "models": [
                    {
                        "id": "claude-sonnet-4-20250514",
                        "name": "Claude Sonnet 4",
                        "max_tokens": 8192,
                        "context_window": 200000,
                        "supports_tools": True,
                        "supports_vision": True,
                    }
                ],
                "rate_limits": {
                    "requests_per_minute": 60,
                    "tokens_per_minute": 100000,
                },
            },
            "openai": {
                "enabled": True,
                "api_base_url": "https://api.openai.com/v1",
                "models": [
                    {
                        "id": "gpt-4o",
                        "name": "GPT-4o",
                        "max_tokens": 16384,
                        "supports_tools": True,
                    }
                ],
            },
        },
        "agent_configs": {
            "dev_worker": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "temperature": 0.2,
                "max_tokens": 8192,
                "system_prompt": "You are a dev agent.",
            }
        },
        "fallback": {
            "enabled": True,
            "provider_order": ["anthropic", "openai", "google", "local"],
            "max_retries": 2,
            "retry_backoff": 1.5,
        },
        "cache": {
            "enabled": True,
            "ttl_seconds": 3600,
        },
        "monitoring": {
            "log_requests": True,
            "log_responses": False,
        },
    }


@pytest.fixture
def config_file(sample_config):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config, f)
        yield Path(f.name)
    os.unlink(f.name)


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_create_model_config(self):
        model = ModelConfig(
            id="claude-sonnet-4-20250514",
            name="Claude Sonnet 4",
            max_tokens=8192,
            context_window=200000,
            supports_tools=True,
            supports_vision=True,
        )
        assert model.id == "claude-sonnet-4-20250514"
        assert model.name == "Claude Sonnet 4"
        assert model.max_tokens == 8192
        assert model.context_window == 200000
        assert model.supports_tools is True
        assert model.supports_vision is True

    def test_default_values(self):
        model = ModelConfig(id="test", name="Test")
        assert model.max_tokens == 4096
        assert model.context_window == 128000
        assert model.supports_tools is False
        assert model.supports_vision is False


class TestProviderConfig:
    """Tests for ProviderConfig dataclass."""

    def test_create_provider_config(self):
        provider = ProviderConfig(
            name="anthropic",
            enabled=True,
            api_base_url="https://api.anthropic.com",
            api_version="2023-06-01",
            models=(ModelConfig(id="claude-sonnet-4-20250514", name="Claude Sonnet 4"),),
            rate_limits=RateLimitConfig(requests_per_minute=60, tokens_per_minute=100000),
        )
        assert provider.name == "anthropic"
        assert provider.enabled is True
        assert provider.api_version == "2023-06-01"
        assert len(provider.models) == 1

    def test_get_model(self):
        provider = ProviderConfig(
            name="test",
            enabled=True,
            api_base_url="https://test.com",
            models=(
                ModelConfig(id="model-1", name="Model 1"),
                ModelConfig(id="model-2", name="Model 2"),
            ),
        )
        model = provider.get_model("model-1")
        assert model is not None
        assert model.id == "model-1"

        missing = provider.get_model("nonexistent")
        assert missing is None

    def test_get_default_model(self):
        provider = ProviderConfig(
            name="test",
            enabled=True,
            api_base_url="https://test.com",
            models=(
                ModelConfig(id="model-1", name="Model 1"),
                ModelConfig(id="model-2", name="Model 2"),
            ),
        )
        default = provider.get_default_model()
        assert default is not None
        assert default.id == "model-1"


class TestAgentLLMConfig:
    """Tests for AgentLLMConfig dataclass."""

    def test_create_agent_config(self):
        config = AgentLLMConfig(
            agent_name="dev_worker",
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            temperature=0.2,
            max_tokens=8192,
            system_prompt="You are a dev agent.",
        )
        assert config.agent_name == "dev_worker"
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.temperature == 0.2


class TestLLMConfigurationManager:
    """Tests for LLMConfigurationManager."""

    def test_load_config(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        manager.load()

        assert manager.default_provider == "anthropic"
        assert manager.get_default_model("anthropic") == "claude-sonnet-4-20250514"

    def test_get_provider(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        provider = manager.get_provider("anthropic")

        assert provider is not None
        assert provider.name == "anthropic"
        assert provider.enabled is True

    def test_get_enabled_providers(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        enabled = manager.get_enabled_providers()

        assert len(enabled) == 2
        names = [p.name for p in enabled]
        assert "anthropic" in names
        assert "openai" in names

    def test_get_agent_config(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        config = manager.get_agent_config("dev_worker")

        assert config is not None
        assert config.agent_name == "dev_worker"
        assert config.provider == "anthropic"
        assert config.temperature == 0.2

    def test_get_agent_config_or_default(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)

        # Get existing config
        config = manager.get_agent_config_or_default("dev_worker")
        assert config.temperature == 0.2

        # Get default for unknown agent
        default = manager.get_agent_config_or_default("unknown_agent")
        assert default.agent_name == "unknown_agent"
        assert default.provider == "anthropic"  # default provider
        assert default.temperature == 0.7  # default temperature

    def test_fallback_config(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        fallback = manager.fallback_config

        assert fallback.enabled is True
        assert fallback.max_retries == 2
        assert fallback.retry_backoff == 1.5
        assert "anthropic" in fallback.provider_order

    def test_cache_config(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        cache = manager.cache_config

        assert cache.enabled is True
        assert cache.ttl_seconds == 3600

    def test_monitoring_config(self, config_file):
        manager = LLMConfigurationManager(config_path=config_file)
        monitoring = manager.monitoring_config

        assert monitoring.log_requests is True
        assert monitoring.log_responses is False

    def test_apply_defaults_when_no_config(self):
        # Use a non-existent path
        manager = LLMConfigurationManager(config_path=Path("/nonexistent/path.yaml"))
        manager.load()

        # Should have defaults
        assert manager.default_provider == "anthropic"
        assert len(manager.get_enabled_providers()) > 0

    def test_get_api_key_from_env(self, config_file, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")

        manager = LLMConfigurationManager(config_path=config_file)
        api_key = manager.get_api_key("anthropic")

        assert api_key == "test-key-123"

    def test_get_api_key_google_fallback(self, config_file, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

        manager = LLMConfigurationManager(config_path=config_file)
        api_key = manager.get_api_key("google")

        assert api_key == "google-key"


class TestGlobalConfigManager:
    """Tests for global config manager functions."""

    def test_get_llm_config_singleton(self):
        config1 = get_llm_config()
        config2 = get_llm_config()
        assert config1 is config2

    def test_reset_llm_config(self):
        config1 = get_llm_config()
        reset_llm_config()
        config2 = get_llm_config()
        assert config1 is not config2
