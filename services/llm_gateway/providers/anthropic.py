"""Anthropic Claude LLM Provider.

This module provides integration with Anthropic's Claude API.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from services.llm_gateway.providers.base import (
    AuthenticationError,
    GenerationConfig,
    GenerationResult,
    Message,
    ModelNotFoundError,
    Provider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)

log = logging.getLogger(__name__)

# Anthropic API constants
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(Provider):
    """Provider for Anthropic's Claude API.

    Supports all Claude models including Claude 3.5 Sonnet, Claude 3 Opus,
    and Claude 3 Haiku with full feature support including:
    - Multi-turn conversations
    - System prompts
    - Tool/function calling
    - Vision (image inputs)
    - JSON mode
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: str = ANTHROPIC_API_URL,
        api_version: str = ANTHROPIC_API_VERSION,
        timeout: float = 120.0,
    ):
        super().__init__("anthropic", api_key)
        self.api_base_url = api_base_url.rstrip("/")
        if not self.api_base_url.endswith("/messages"):
            self.api_base_url = f"{self.api_base_url}/v1/messages"
        self.api_version = api_version
        self.timeout = timeout

    def _get_default_model(self) -> str:
        return DEFAULT_MODEL

    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Generate a response using Anthropic's Claude API.

        Args:
            messages: List of conversation messages
            config: Generation configuration

        Returns:
            GenerationResult with Claude's response
        """
        if not self.api_key:
            raise AuthenticationError("Anthropic API key is required")

        start_time = time.time()

        # Build request payload
        payload = self._build_request_payload(messages, config)

        # Make API request
        try:
            response = self._make_request(payload)
            result = self._parse_response(response, config.model, start_time)
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
        except httpx.TimeoutException:
            raise ProviderError(f"Request timed out after {self.timeout}s", retryable=True)
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {str(e)}", retryable=True)

    def _build_request_payload(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> Dict[str, Any]:
        """Build the API request payload."""
        # Convert messages to Anthropic format
        anthropic_messages = []
        system_prompt = config.system_prompt

        for msg in messages:
            if msg.role == "system":
                # Anthropic uses a separate system parameter
                system_prompt = msg.content
                continue

            anthropic_msg: Dict[str, Any] = {
                "role": msg.role if msg.role != "assistant" else "assistant",
                "content": msg.content,
            }

            # Handle tool results
            if msg.role == "user" and msg.tool_call_id:
                anthropic_msg["content"] = [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ]

            anthropic_messages.append(anthropic_msg)

        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": anthropic_messages,
            "max_tokens": config.max_tokens,
        }

        # Add optional parameters
        if system_prompt:
            payload["system"] = system_prompt

        if config.temperature is not None:
            payload["temperature"] = config.temperature

        if config.top_p is not None:
            payload["top_p"] = config.top_p

        if config.stop_sequences:
            payload["stop_sequences"] = config.stop_sequences

        # Add tools if provided
        if config.tools:
            payload["tools"] = self._convert_tools(config.tools)

            if config.tool_choice:
                if config.tool_choice == "auto":
                    payload["tool_choice"] = {"type": "auto"}
                elif config.tool_choice == "required":
                    payload["tool_choice"] = {"type": "any"}
                elif config.tool_choice == "none":
                    # Don't include tools if none is specified
                    del payload["tools"]
                else:
                    # Specific tool name
                    payload["tool_choice"] = {"type": "tool", "name": config.tool_choice}

        return payload

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools from OpenAI format to Anthropic format if needed."""
        anthropic_tools = []
        for tool in tools:
            if "function" in tool:
                # OpenAI format - convert to Anthropic format
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                # Already in Anthropic format
                anthropic_tools.append(tool)
        return anthropic_tools

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make the HTTP request to Anthropic's API."""
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "anthropic-version": self.api_version,
        }

        log.debug(f"Anthropic request: model={payload.get('model')}, max_tokens={payload.get('max_tokens')}")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.api_base_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _parse_response(
        self,
        response: Dict[str, Any],
        model: str,
        start_time: float,
    ) -> GenerationResult:
        """Parse Anthropic's API response."""
        content_blocks = response.get("content", [])
        text_content = ""
        tool_calls = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        # Parse usage
        usage_data = response.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage_data.get("cache_creation_input_tokens", 0),
        )

        # Map stop reason
        stop_reason = response.get("stop_reason", "stop")
        finish_reason_map = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }
        finish_reason = finish_reason_map.get(stop_reason, stop_reason)

        latency_ms = (time.time() - start_time) * 1000

        return GenerationResult(
            content=text_content,
            usage=usage,
            model=response.get("model", model),
            finish_reason=finish_reason,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors from Anthropic's API."""
        status_code = error.response.status_code
        try:
            error_body = error.response.json()
            error_message = error_body.get("error", {}).get("message", str(error))
        except Exception:
            error_message = str(error)

        if status_code == 401:
            raise AuthenticationError(f"Invalid API key: {error_message}")
        elif status_code == 429:
            # Try to extract retry-after header
            retry_after = error.response.headers.get("retry-after")
            retry_seconds = float(retry_after) if retry_after else None
            raise RateLimitError(f"Rate limit exceeded: {error_message}", retry_after=retry_seconds)
        elif status_code == 404:
            raise ModelNotFoundError(f"Model not found: {error_message}")
        elif status_code == 400:
            raise ProviderError(f"Bad request: {error_message}", retryable=False, status_code=400)
        elif status_code >= 500:
            raise ProviderError(f"Server error: {error_message}", retryable=True, status_code=status_code)
        else:
            raise ProviderError(f"API error ({status_code}): {error_message}", retryable=False, status_code=status_code)

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts, use the API's
        token counting endpoint when available.
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
