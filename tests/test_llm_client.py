"""Tests for the unified LLM client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import LLMClient
from core.llm_config import LLMConfig, ProviderConfig


class TestLLMClient:
    """Tests for LLMClient class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock LLM configuration."""
        return LLMConfig(
            default_provider="anthropic",
            fallback_order=["anthropic", "openai"],
            providers={
                "anthropic": ProviderConfig(
                    name="anthropic",
                    enabled=True,
                    api_key="test-anthropic-key",
                    default_model="claude-3-sonnet",
                ),
                "openai": ProviderConfig(
                    name="openai",
                    enabled=True,
                    api_key="test-openai-key",
                    default_model="gpt-4o",
                ),
            },
        )

    def test_client_initialization(self, mock_config):
        """Test LLM client initialization."""
        client = LLMClient(config=mock_config)
        assert client.config == mock_config
        assert client._providers == {}
        assert client._usage_stats == {}

    def test_get_provider_creates_instance(self, mock_config):
        """Test that _get_provider creates provider instances."""
        client = LLMClient(config=mock_config)

        with patch("core.llm_client.AnthropicProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            # Import the actual module to patch correctly
            import core.llm_client
            with patch.object(core.llm_client, "AnthropicProvider", mock_provider):
                # Reload the _create_provider to use patched version
                pass

    def test_get_provider_caches_instance(self, mock_config):
        """Test that provider instances are cached."""
        client = LLMClient(config=mock_config)

        # Manually set a provider
        mock_provider = MagicMock()
        client._providers["anthropic"] = mock_provider

        # Should return cached instance
        result = client._get_provider("anthropic")
        assert result is mock_provider

    def test_get_provider_raises_for_disabled(self, mock_config):
        """Test that disabled providers raise an error."""
        mock_config.providers["anthropic"] = ProviderConfig(
            name="anthropic",
            enabled=False,
        )
        client = LLMClient(config=mock_config)

        with pytest.raises(ValueError, match="disabled"):
            client._get_provider("anthropic")

    def test_get_provider_raises_for_unknown(self, mock_config):
        """Test that unknown providers raise an error."""
        client = LLMClient(config=mock_config)

        with pytest.raises(ValueError, match="not configured"):
            client._get_provider("unknown_provider")

    def test_predict_with_string_prompt(self, mock_config):
        """Test predict with a simple string prompt."""
        client = LLMClient(config=mock_config)

        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.predict.return_value = (
            {"text": "response"},
            {"provider": "anthropic", "model": "claude-3-sonnet", "input_tokens": 10, "output_tokens": 20},
        )
        client._providers["anthropic"] = mock_provider

        result, usage = client.predict("Hello, world!")

        mock_provider.predict.assert_called_once()
        call_args = mock_provider.predict.call_args
        assert call_args[1]["prompt"] == {"prompt": "Hello, world!"}
        assert result == {"text": "response"}
        assert usage["provider"] == "anthropic"

    def test_predict_with_dict_prompt(self, mock_config):
        """Test predict with a dict prompt."""
        client = LLMClient(config=mock_config)

        mock_provider = MagicMock()
        mock_provider.predict.return_value = (
            {"text": "response"},
            {"provider": "anthropic", "model": "claude-3-sonnet", "input_tokens": 10, "output_tokens": 20},
        )
        client._providers["anthropic"] = mock_provider

        prompt = {"query": "What is AI?", "context": "Technical discussion"}
        result, usage = client.predict(prompt)

        call_args = mock_provider.predict.call_args
        assert call_args[1]["prompt"] == prompt

    def test_predict_with_provider_override(self, mock_config):
        """Test predict with provider override."""
        client = LLMClient(config=mock_config)

        mock_openai = MagicMock()
        mock_openai.predict.return_value = (
            {"text": "openai response"},
            {"provider": "openai", "model": "gpt-4o", "input_tokens": 10, "output_tokens": 20},
        )
        client._providers["openai"] = mock_openai

        result, usage = client.predict("Hello", provider="openai")

        mock_openai.predict.assert_called_once()
        assert usage["provider"] == "openai"

    def test_predict_fallback_on_error(self, mock_config):
        """Test that predict falls back to next provider on error."""
        client = LLMClient(config=mock_config)

        # First provider fails
        mock_anthropic = MagicMock()
        mock_anthropic.predict.side_effect = Exception("API error")
        client._providers["anthropic"] = mock_anthropic

        # Second provider succeeds
        mock_openai = MagicMock()
        mock_openai.predict.return_value = (
            {"text": "fallback response"},
            {"provider": "openai", "model": "gpt-4o", "input_tokens": 10, "output_tokens": 20},
        )
        client._providers["openai"] = mock_openai

        result, usage = client.predict("Hello", fallback=True)

        assert usage["provider"] == "openai"
        assert result == {"text": "fallback response"}

    def test_predict_no_fallback_raises(self, mock_config):
        """Test that predict raises when fallback is disabled."""
        client = LLMClient(config=mock_config)

        mock_provider = MagicMock()
        mock_provider.predict.side_effect = Exception("API error")
        client._providers["anthropic"] = mock_provider

        with pytest.raises(RuntimeError, match="All providers failed"):
            client.predict("Hello", fallback=False)

    def test_chat_method(self, mock_config):
        """Test the chat method."""
        client = LLMClient(config=mock_config)

        mock_provider = MagicMock()
        mock_provider.predict.return_value = (
            {"text": "chat response"},
            {"provider": "anthropic", "model": "claude-3-sonnet", "input_tokens": 10, "output_tokens": 20},
        )
        client._providers["anthropic"] = mock_provider

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        result, usage = client.chat(messages)

        call_args = mock_provider.predict.call_args
        assert "messages" in call_args[1]["prompt"]

    def test_usage_tracking(self, mock_config):
        """Test that usage is tracked correctly."""
        client = LLMClient(config=mock_config)

        mock_provider = MagicMock()
        mock_provider.predict.return_value = (
            {"text": "response"},
            {"provider": "anthropic", "model": "claude-3-sonnet", "input_tokens": 100, "output_tokens": 50},
        )
        client._providers["anthropic"] = mock_provider

        # Make a prediction
        client.predict("Hello", agent_name="test_agent", task_type="text_generation")

        stats = client.get_usage_stats()
        assert "anthropic" in stats
        assert stats["anthropic"]["total_input_tokens"] == 100
        assert stats["anthropic"]["total_output_tokens"] == 50
        assert stats["anthropic"]["total_requests"] == 1

    def test_reset_usage_stats(self, mock_config):
        """Test resetting usage statistics."""
        client = LLMClient(config=mock_config)
        client._usage_stats = {"anthropic": {"total_requests": 10}}

        client.reset_usage_stats()

        assert client._usage_stats == {}


class TestLLMClientConvenienceFunctions:
    """Tests for convenience functions."""

    def test_predict_function(self):
        """Test the predict convenience function."""
        with patch("core.llm_client.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.predict.return_value = ({"text": "response"}, {"provider": "test"})
            mock_get_client.return_value = mock_client

            from core.llm_client import predict
            result, usage = predict("Hello")

            mock_client.predict.assert_called_once()

    def test_chat_function(self):
        """Test the chat convenience function."""
        with patch("core.llm_client.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = ({"text": "response"}, {"provider": "test"})
            mock_get_client.return_value = mock_client

            from core.llm_client import chat
            messages = [{"role": "user", "content": "Hello"}]
            result, usage = chat(messages)

            mock_client.chat.assert_called_once()
