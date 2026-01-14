"""Tests for LLM configuration loading and management."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from core.llm_config import (
    LLMConfig,
    ProviderConfig,
    AgentConfig,
    ModelConfig,
    load_config,
    _expand_env_vars,
)


class TestEnvVarExpansion:
    """Tests for environment variable expansion."""

    def test_expand_simple_var(self, monkeypatch):
        """Test expanding a simple environment variable."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = _expand_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_expand_var_with_default(self, monkeypatch):
        """Test expanding variable with default value."""
        # Variable not set, should use default
        result = _expand_env_vars("${UNSET_VAR:-default_value}")
        assert result == "default_value"

        # Variable set, should use actual value
        monkeypatch.setenv("SET_VAR", "actual_value")
        result = _expand_env_vars("${SET_VAR:-default_value}")
        assert result == "actual_value"

    def test_expand_in_dict(self, monkeypatch):
        """Test expanding variables in dictionaries."""
        monkeypatch.setenv("API_KEY", "secret123")
        data = {
            "key": "${API_KEY}",
            "nested": {
                "value": "${API_KEY}",
            },
        }
        result = _expand_env_vars(data)
        assert result["key"] == "secret123"
        assert result["nested"]["value"] == "secret123"

    def test_expand_in_list(self, monkeypatch):
        """Test expanding variables in lists."""
        monkeypatch.setenv("ITEM", "value")
        data = ["${ITEM}", "${ITEM}"]
        result = _expand_env_vars(data)
        assert result == ["value", "value"]


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_default_config_when_no_file(self):
        """Test that default config is returned when no file exists."""
        config = load_config("/nonexistent/path.yaml")
        assert isinstance(config, LLMConfig)
        assert config.default_provider == "anthropic"

    def test_load_config_from_yaml(self):
        """Test loading configuration from YAML file."""
        config_data = {
            "global": {
                "default_provider": "openai",
                "fallback_order": ["openai", "anthropic"],
                "timeout_seconds": 60,
            },
            "providers": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-key",
                    "default_model": "gpt-4o",
                    "models": {
                        "gpt-4o": {
                            "max_tokens": 4096,
                            "temperature": 0.7,
                        },
                    },
                },
            },
            "agent_overrides": {
                "test_agent": {
                    "provider": "anthropic",
                    "model": "claude-3-sonnet",
                    "temperature": 0.5,
                },
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.default_provider == "openai"
            assert config.fallback_order == ["openai", "anthropic"]
            assert config.timeout_seconds == 60
            assert "openai" in config.providers
            assert config.providers["openai"].default_model == "gpt-4o"
            assert "test_agent" in config.agent_overrides
            assert config.agent_overrides["test_agent"].provider == "anthropic"
        finally:
            os.unlink(temp_path)


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_get_effective_config_defaults(self):
        """Test getting effective config with no overrides."""
        config = LLMConfig(
            default_provider="anthropic",
            providers={
                "anthropic": ProviderConfig(
                    name="anthropic",
                    default_model="claude-3-sonnet",
                ),
            },
        )

        effective = config.get_effective_config()
        assert effective["provider"] == "anthropic"
        assert effective["model"] == "claude-3-sonnet"
        assert effective["temperature"] == 0.7
        assert effective["max_tokens"] == 4096

    def test_get_effective_config_with_agent_override(self):
        """Test getting effective config with agent-specific override."""
        config = LLMConfig(
            default_provider="anthropic",
            providers={
                "anthropic": ProviderConfig(
                    name="anthropic",
                    default_model="claude-3-sonnet",
                ),
                "openai": ProviderConfig(
                    name="openai",
                    default_model="gpt-4o",
                ),
            },
            agent_overrides={
                "my_agent": AgentConfig(
                    agent_name="my_agent",
                    provider="openai",
                    model="gpt-4o-mini",
                    temperature=0.3,
                ),
            },
        )

        effective = config.get_effective_config(agent_name="my_agent")
        assert effective["provider"] == "openai"
        assert effective["model"] == "gpt-4o-mini"
        assert effective["temperature"] == 0.3

    def test_get_effective_config_with_task_type_override(self):
        """Test getting effective config with task type override."""
        config = LLMConfig(
            default_provider="anthropic",
            providers={
                "anthropic": ProviderConfig(
                    name="anthropic",
                    default_model="claude-3-sonnet",
                ),
            },
            task_type_overrides={
                "code_generation": AgentConfig(
                    agent_name="code_generation",
                    temperature=0.2,
                    max_tokens=8192,
                ),
            },
        )

        effective = config.get_effective_config(task_type="code_generation")
        assert effective["temperature"] == 0.2
        assert effective["max_tokens"] == 8192

    def test_agent_override_takes_precedence_over_task_type(self):
        """Test that agent override takes precedence over task type."""
        config = LLMConfig(
            default_provider="anthropic",
            providers={
                "anthropic": ProviderConfig(
                    name="anthropic",
                    default_model="claude-3-sonnet",
                ),
            },
            agent_overrides={
                "my_agent": AgentConfig(
                    agent_name="my_agent",
                    temperature=0.1,
                ),
            },
            task_type_overrides={
                "code_generation": AgentConfig(
                    agent_name="code_generation",
                    temperature=0.5,
                ),
            },
        )

        effective = config.get_effective_config(
            agent_name="my_agent",
            task_type="code_generation",
        )
        # Agent override should win
        assert effective["temperature"] == 0.1


class TestProviderConfig:
    """Tests for ProviderConfig dataclass."""

    def test_provider_config_creation(self):
        """Test creating a provider config."""
        config = ProviderConfig(
            name="anthropic",
            enabled=True,
            api_key="test-key",
            default_model="claude-3-sonnet",
        )
        assert config.name == "anthropic"
        assert config.enabled is True
        assert config.api_key == "test-key"
        assert config.default_model == "claude-3-sonnet"

    def test_provider_config_with_models(self):
        """Test provider config with model definitions."""
        config = ProviderConfig(
            name="openai",
            models={
                "gpt-4o": ModelConfig(
                    name="gpt-4o",
                    max_tokens=16384,
                    supports_vision=True,
                    supports_tools=True,
                ),
            },
        )
        assert "gpt-4o" in config.models
        assert config.models["gpt-4o"].max_tokens == 16384
        assert config.models["gpt-4o"].supports_vision is True


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_model_config_defaults(self):
        """Test model config default values."""
        config = ModelConfig(name="test-model")
        assert config.max_tokens == 4096
        assert config.temperature == 0.7
        assert config.supports_vision is False
        assert config.supports_tools is False
        assert config.context_window == 8192
        assert config.cost_per_1k_input_tokens == 0.0
        assert config.cost_per_1k_output_tokens == 0.0

    def test_model_config_with_values(self):
        """Test model config with custom values."""
        config = ModelConfig(
            name="gpt-4o",
            max_tokens=16384,
            temperature=0.5,
            supports_vision=True,
            supports_tools=True,
            context_window=128000,
            cost_per_1k_input_tokens=0.005,
            cost_per_1k_output_tokens=0.015,
        )
        assert config.max_tokens == 16384
        assert config.temperature == 0.5
        assert config.supports_vision is True
        assert config.supports_tools is True
        assert config.context_window == 128000
        assert config.cost_per_1k_input_tokens == 0.005
        assert config.cost_per_1k_output_tokens == 0.015
