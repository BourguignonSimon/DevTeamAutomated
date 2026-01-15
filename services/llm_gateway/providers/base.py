"""Base LLM Provider Interface.

This module defines the abstract interface that all LLM providers must implement.
"""
from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class ProviderError(Exception):
    """Exception raised when a provider operation fails."""

    def __init__(self, message: str, retryable: bool = True, status_code: Optional[int] = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class RateLimitError(ProviderError):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message, retryable=True, status_code=429)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Exception raised when authentication fails."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False, status_code=401)


class ModelNotFoundError(ProviderError):
    """Exception raised when the requested model is not found."""

    def __init__(self, message: str):
        super().__init__(message, retryable=False, status_code=404)


@dataclass
class Message:
    """A message in a conversation."""
    role: str  # "system", "user", "assistant"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class GenerationConfig:
    """Configuration for LLM generation."""
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: Optional[float] = None
    stop_sequences: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None  # "auto", "required", "none", or specific tool name
    response_format: Optional[Dict[str, Any]] = None  # For JSON mode
    seed: Optional[int] = None  # For reproducibility


@dataclass
class TokenUsage:
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class GenerationResult:
    """Result of an LLM generation."""
    content: str
    usage: TokenUsage
    model: str
    finish_reason: str  # "stop", "length", "tool_calls", "content_filter"
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0


class Provider(ABC):
    """Abstract base class for LLM providers.

    All LLM providers must implement this interface to be used
    in the multi-provider system.
    """

    def __init__(self, name: str, api_key: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self._client: Any = None

    @abstractmethod
    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            config: Generation configuration

        Returns:
            GenerationResult with the response

        Raises:
            ProviderError: If generation fails
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If authentication fails
        """
        raise NotImplementedError

    def predict(self, prompt: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Legacy predict interface for backward compatibility.

        Converts the prompt dict to messages and calls generate().

        Args:
            prompt: Dictionary with prompt data

        Returns:
            Tuple of (result_json, usage_dict)
        """
        # Extract content from prompt
        content_parts = []
        if prompt.get("extracted_text"):
            content_parts.append(f"Text:\n{prompt['extracted_text']}")
        if prompt.get("extracted_table"):
            import json
            content_parts.append(f"Table:\n{json.dumps(prompt['extracted_table'], indent=2)}")

        # Build messages
        messages = [
            Message(
                role="user",
                content="\n\n".join(content_parts) if content_parts else str(prompt),
            )
        ]

        # Create config with defaults
        config = GenerationConfig(
            model=prompt.get("model", self._get_default_model()),
            temperature=prompt.get("temperature", 0.3),
            max_tokens=prompt.get("max_tokens", 4096),
            system_prompt=prompt.get("system_prompt"),
        )

        # Generate response
        result = self.generate(messages, config)

        # Parse JSON from response
        try:
            import json
            result_json = json.loads(result.content)
        except (json.JSONDecodeError, TypeError):
            result_json = {"raw_response": result.content}

        usage = {
            "tokens_in": result.usage.input_tokens,
            "tokens_out": result.usage.output_tokens,
            "total_tokens": result.usage.total_tokens,
        }

        return result_json, usage

    def _get_default_model(self) -> str:
        """Get the default model for this provider."""
        return "default"

    def validate_api_key(self) -> bool:
        """Validate that API key is present and properly formatted."""
        return bool(self.api_key and len(self.api_key) > 10)

    @staticmethod
    def safe_hash(content: str) -> str:
        """Create a SHA-256 hash of content for caching/deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def health_check(self) -> bool:
        """Check if the provider is healthy and accessible."""
        try:
            # Simple generation to test connectivity
            result = self.generate(
                messages=[Message(role="user", content="Hi")],
                config=GenerationConfig(model=self._get_default_model(), max_tokens=10),
            )
            return bool(result.content)
        except Exception as e:
            log.warning(f"Health check failed for {self.name}: {e}")
            return False


class AsyncProvider(Provider):
    """Base class for providers with async support."""

    @abstractmethod
    async def generate_async(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Async version of generate."""
        raise NotImplementedError

    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Sync wrapper around async generate."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.generate_async(messages, config)
                )
                return future.result()
        else:
            return asyncio.run(self.generate_async(messages, config))
