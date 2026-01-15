"""Tests for LLM providers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.llm_gateway.providers.base import Provider, ProviderError


class TestProviderBase:
    """Tests for base Provider class."""

    def test_provider_initialization(self):
        """Test provider initialization."""
        provider = Provider("test")
        assert provider.name == "test"

    def test_predict_not_implemented(self):
        """Test that predict raises NotImplementedError."""
        provider = Provider("test")
        with pytest.raises(NotImplementedError):
            provider.predict({})

    def test_safe_hash(self):
        """Test safe_hash static method."""
        hash1 = Provider.safe_hash("test content")
        hash2 = Provider.safe_hash("test content")
        hash3 = Provider.safe_hash("different content")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA256 hex length


class TestAnthropicProvider:
    """Tests for Anthropic provider."""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults."""
        from services.llm_gateway.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        assert provider.name == "anthropic"
        assert provider.api_key == "test-key"
        assert provider.default_model == "claude-3-5-sonnet-20241022"
        assert provider.timeout_seconds == 120
        assert provider.max_retries == 3

    def test_initialization_custom(self):
        """Test provider initialization with custom values."""
        from services.llm_gateway.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(
            api_key="test-key",
            base_url="https://custom.api.com",
            default_model="claude-3-opus",
            timeout_seconds=60,
            max_retries=5,
        )
        assert provider.base_url == "https://custom.api.com"
        assert provider.default_model == "claude-3-opus"
        assert provider.timeout_seconds == 60
        assert provider.max_retries == 5

    def test_predict_without_api_key_raises(self):
        """Test that predict raises without API key."""
        from services.llm_gateway.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key=None)
        with pytest.raises(ProviderError, match="API key is required"):
            provider.predict({"prompt": "test"})

    def test_build_messages_from_prompt(self):
        """Test building messages from prompt dict."""
        from services.llm_gateway.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test")
        prompt = {"prompt": "Hello, world!"}
        messages = provider._build_messages(prompt)

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "Hello, world!" in messages[0]["content"]

    def test_build_messages_from_messages(self):
        """Test building messages from message list."""
        from services.llm_gateway.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test")
        prompt = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
        }
        messages = provider._build_messages(prompt)

        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi there"


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults."""
        from services.llm_gateway.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        assert provider.name == "openai"
        assert provider.api_key == "test-key"
        assert provider.default_model == "gpt-4o"

    def test_predict_without_api_key_raises(self):
        """Test that predict raises without API key."""
        from services.llm_gateway.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=None)
        with pytest.raises(ProviderError, match="API key is required"):
            provider.predict({"prompt": "test"})

    def test_build_request_body_regular_model(self):
        """Test building request body for regular models."""
        from services.llm_gateway.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test")
        body = provider._build_request_body(
            prompt={"prompt": "Hello"},
            model="gpt-4o",
            max_tokens=1000,
            temperature=0.5,
        )

        assert body["model"] == "gpt-4o"
        assert body["max_tokens"] == 1000
        assert body["temperature"] == 0.5

    def test_build_request_body_o1_model(self):
        """Test building request body for o1 models."""
        from services.llm_gateway.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test")
        body = provider._build_request_body(
            prompt={"prompt": "Hello"},
            model="o1-mini",
            max_tokens=1000,
        )

        assert body["model"] == "o1-mini"
        # o1 models use max_completion_tokens instead of max_tokens
        assert "max_completion_tokens" in body
        assert "temperature" not in body  # o1 doesn't support temperature


class TestGeminiProvider:
    """Tests for Gemini provider."""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults."""
        from services.llm_gateway.providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-key")
        assert provider.name == "google"
        assert provider.api_key == "test-key"
        assert provider.default_model == "gemini-1.5-pro"

    def test_predict_without_api_key_raises(self):
        """Test that predict raises without API key."""
        from services.llm_gateway.providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key=None)
        with pytest.raises(ProviderError, match="API key is required"):
            provider.predict({"prompt": "test"})

    def test_build_safety_settings(self):
        """Test building safety settings."""
        from services.llm_gateway.providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test")
        settings = provider._build_safety_settings()

        assert len(settings) == 4  # Four harm categories
        for setting in settings:
            assert "category" in setting
            assert "threshold" in setting

    def test_build_contents_from_prompt(self):
        """Test building contents from prompt dict."""
        from services.llm_gateway.providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test")
        prompt = {"prompt": "Hello, world!"}
        contents = provider._build_contents(prompt)

        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert "Hello, world!" in contents[0]["parts"][0]["text"]


class TestLocalProvider:
    """Tests for Local LLM provider."""

    def test_initialization_defaults(self):
        """Test provider initialization with defaults."""
        from services.llm_gateway.providers.local import LocalProvider

        provider = LocalProvider()
        assert provider.name == "local"
        assert "localhost" in provider.base_url
        assert provider.default_model == "llama3.1:8b"

    def test_initialization_with_server_type(self):
        """Test provider initialization with different server types."""
        from services.llm_gateway.providers.local import LocalProvider, ServerType

        # Ollama
        provider = LocalProvider(server_type="ollama")
        assert provider.server_type == ServerType.OLLAMA

        # LocalAI
        provider = LocalProvider(server_type="localai")
        assert provider.server_type == ServerType.LOCALAI

    def test_get_endpoint_ollama(self):
        """Test getting endpoint for Ollama."""
        from services.llm_gateway.providers.local import LocalProvider

        provider = LocalProvider(server_type="ollama", base_url="http://localhost:11434")
        endpoint = provider._get_endpoint()

        assert endpoint == "http://localhost:11434/api/chat"

    def test_get_endpoint_openai_compatible(self):
        """Test getting endpoint for OpenAI-compatible server."""
        from services.llm_gateway.providers.local import LocalProvider

        provider = LocalProvider(server_type="openai_compatible", base_url="http://localhost:8000")
        endpoint = provider._get_endpoint()

        assert endpoint == "http://localhost:8000/v1/chat/completions"

    def test_is_available_returns_false_on_connection_error(self):
        """Test is_available returns False when server is not reachable."""
        from services.llm_gateway.providers.local import LocalProvider

        provider = LocalProvider(base_url="http://localhost:99999")
        assert provider.is_available() is False


class TestProviderError:
    """Tests for ProviderError exception."""

    def test_provider_error_message(self):
        """Test ProviderError with message."""
        error = ProviderError("Test error message")
        assert str(error) == "Test error message"

    def test_provider_error_inheritance(self):
        """Test ProviderError inherits from Exception."""
        error = ProviderError("Test")
        assert isinstance(error, Exception)
