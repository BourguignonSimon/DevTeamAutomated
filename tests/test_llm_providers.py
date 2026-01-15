"""Tests for LLM provider implementations."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.llm_gateway.providers import (
    AnthropicProvider,
    AuthenticationError,
    GeminiProvider,
    GenerationConfig,
    GenerationResult,
    LocalProvider,
    Message,
    ModelNotFoundError,
    OpenAIProvider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)
from services.llm_gateway.providers.fake import FakeProvider


class TestMessage:
    """Tests for Message dataclass."""

    def test_create_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_message_with_tool_calls(self):
        tool_calls = [{"id": "call_1", "function": {"name": "test"}}]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)
        assert msg.tool_calls == tool_calls


class TestGenerationConfig:
    """Tests for GenerationConfig dataclass."""

    def test_create_config(self):
        config = GenerationConfig(
            model="claude-sonnet-4-20250514",
            temperature=0.7,
            max_tokens=4096,
        )
        assert config.model == "claude-sonnet-4-20250514"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096

    def test_default_values(self):
        config = GenerationConfig(model="test")
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.tools is None
        assert config.stop_sequences == []


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_create_usage(self):
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150


class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_create_result(self):
        result = GenerationResult(
            content="Hello!",
            usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            model="test-model",
            finish_reason="stop",
        )
        assert result.content == "Hello!"
        assert result.model == "test-model"
        assert result.finish_reason == "stop"


class TestFakeProvider:
    """Tests for FakeProvider."""

    def test_predict_basic(self):
        provider = FakeProvider()
        prompt = {
            "extracted_text": "Test order",
            "extracted_table": [{"SKU": "ABC123", "Qty": 5}],
            "order_id": "order-123",
        }

        result, usage = provider.predict(prompt)

        assert "order_draft" in result
        assert result["order_draft"]["order_id"] == "order-123"
        assert usage["tokens_in"] == 100
        assert usage["tokens_out"] == 200

    def test_predict_with_lines(self):
        provider = FakeProvider()
        prompt = {
            "extracted_table": [
                {"SKU": "SKU1", "Qty": 1},
                {"SKU": "SKU2", "Qty": 2},
            ]
        }

        result, _ = provider.predict(prompt)

        lines = result["order_draft"]["lines"]
        assert len(lines) == 2
        assert lines[0]["sku"] == "SKU1"
        assert lines[1]["sku"] == "SKU2"


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_init(self):
        provider = AnthropicProvider(api_key="test-key")
        assert provider.name == "anthropic"
        assert provider.api_key == "test-key"

    def test_no_api_key_raises(self):
        provider = AnthropicProvider(api_key=None)
        messages = [Message(role="user", content="Hello")]
        config = GenerationConfig(model="claude-sonnet-4-20250514")

        with pytest.raises(AuthenticationError):
            provider.generate(messages, config)

    def test_validate_api_key(self):
        valid_provider = AnthropicProvider(api_key="sk-ant-valid-key-12345")
        assert valid_provider.validate_api_key() is True

        invalid_provider = AnthropicProvider(api_key="short")
        assert invalid_provider.validate_api_key() is False

    @patch("services.llm_gateway.providers.anthropic.httpx.Client")
    def test_generate_success(self, mock_client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Hello!"}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        provider = AnthropicProvider(api_key="test-key")
        messages = [Message(role="user", content="Hi")]
        config = GenerationConfig(model="claude-sonnet-4-20250514")

        result = provider.generate(messages, config)

        assert result.content == "Hello!"
        assert result.usage.input_tokens == 10


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_init(self):
        provider = OpenAIProvider(api_key="test-key")
        assert provider.name == "openai"
        assert provider.api_key == "test-key"

    def test_no_api_key_raises(self):
        provider = OpenAIProvider(api_key=None)
        messages = [Message(role="user", content="Hello")]
        config = GenerationConfig(model="gpt-4o")

        with pytest.raises(AuthenticationError):
            provider.generate(messages, config)

    @patch("services.llm_gateway.providers.openai.httpx.Client")
    def test_generate_success(self, mock_client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "model": "gpt-4o",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        provider = OpenAIProvider(api_key="test-key")
        messages = [Message(role="user", content="Hi")]
        config = GenerationConfig(model="gpt-4o")

        result = provider.generate(messages, config)

        assert result.content == "Hello!"
        assert result.usage.input_tokens == 10


class TestGeminiProvider:
    """Tests for GeminiProvider."""

    def test_init(self):
        provider = GeminiProvider(api_key="test-key")
        assert provider.name == "gemini"
        assert provider.api_key == "test-key"

    def test_no_api_key_raises(self):
        provider = GeminiProvider(api_key=None)
        messages = [Message(role="user", content="Hello")]
        config = GenerationConfig(model="gemini-2.0-flash")

        with pytest.raises(AuthenticationError):
            provider.generate(messages, config)

    @patch("services.llm_gateway.providers.gemini.httpx.Client")
    def test_generate_success(self, mock_client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "Hello!"}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        provider = GeminiProvider(api_key="test-key")
        messages = [Message(role="user", content="Hi")]
        config = GenerationConfig(model="gemini-2.0-flash")

        result = provider.generate(messages, config)

        assert result.content == "Hello!"
        assert result.usage.input_tokens == 10


class TestLocalProvider:
    """Tests for LocalProvider."""

    def test_init_default(self):
        provider = LocalProvider()
        assert provider.name == "local"
        assert "11434" in provider.api_base_url

    def test_init_custom_url(self):
        provider = LocalProvider(api_base_url="http://localhost:1234/v1/chat/completions")
        assert "1234" in provider.api_base_url

    def test_auto_detect_ollama_native(self):
        provider = LocalProvider(api_base_url="http://localhost:11434/api/chat")
        assert provider.use_ollama_native is True

    @patch("services.llm_gateway.providers.local.httpx.Client")
    def test_generate_openai_compatible(self, mock_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hello from Ollama!"},
                    "finish_reason": "stop",
                }
            ],
            "model": "llama3.2:latest",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client.return_value = mock_client_instance

        provider = LocalProvider()
        messages = [Message(role="user", content="Hi")]
        config = GenerationConfig(model="llama3.2:latest")

        result = provider.generate(messages, config)

        assert result.content == "Hello from Ollama!"


class TestProviderErrors:
    """Tests for provider error classes."""

    def test_provider_error(self):
        error = ProviderError("Test error", retryable=True, status_code=500)
        assert str(error) == "Test error"
        assert error.retryable is True
        assert error.status_code == 500

    def test_rate_limit_error(self):
        error = RateLimitError("Rate limited", retry_after=30.0)
        assert error.retryable is True
        assert error.status_code == 429
        assert error.retry_after == 30.0

    def test_authentication_error(self):
        error = AuthenticationError("Invalid key")
        assert error.retryable is False
        assert error.status_code == 401

    def test_model_not_found_error(self):
        error = ModelNotFoundError("Model not found")
        assert error.retryable is False
        assert error.status_code == 404
