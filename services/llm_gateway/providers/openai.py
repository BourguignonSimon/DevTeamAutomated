"""OpenAI GPT LLM Provider.

This module provides integration with OpenAI's GPT API.
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

# OpenAI API constants
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(Provider):
    """Provider for OpenAI's GPT API.

    Supports all GPT models including GPT-4o, GPT-4 Turbo, and o1
    with full feature support including:
    - Multi-turn conversations
    - System prompts
    - Tool/function calling
    - Vision (image inputs)
    - JSON mode
    - Structured outputs
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: str = OPENAI_API_URL,
        organization: Optional[str] = None,
        timeout: float = 120.0,
    ):
        super().__init__("openai", api_key)
        self.api_base_url = api_base_url
        self.organization = organization
        self.timeout = timeout

    def _get_default_model(self) -> str:
        return DEFAULT_MODEL

    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Generate a response using OpenAI's GPT API.

        Args:
            messages: List of conversation messages
            config: Generation configuration

        Returns:
            GenerationResult with GPT's response
        """
        if not self.api_key:
            raise AuthenticationError("OpenAI API key is required")

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
        # Convert messages to OpenAI format
        openai_messages = []

        # Add system prompt if provided
        if config.system_prompt:
            openai_messages.append({
                "role": "system",
                "content": config.system_prompt,
            })

        for msg in messages:
            openai_msg: Dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }

            # Handle tool calls in assistant messages
            if msg.role == "assistant" and msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls

            # Handle tool results
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id

            # Add name if provided
            if msg.name:
                openai_msg["name"] = msg.name

            openai_messages.append(openai_msg)

        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": openai_messages,
        }

        # Check if this is an o1 model (reasoning model with different parameters)
        is_o1_model = config.model.startswith("o1")

        # Add max_tokens (different parameter name for o1)
        if is_o1_model:
            payload["max_completion_tokens"] = config.max_tokens
        else:
            payload["max_tokens"] = config.max_tokens

        # Temperature and top_p not supported for o1 models
        if not is_o1_model:
            if config.temperature is not None:
                payload["temperature"] = config.temperature

            if config.top_p is not None:
                payload["top_p"] = config.top_p

        if config.stop_sequences:
            payload["stop"] = config.stop_sequences

        if config.seed is not None:
            payload["seed"] = config.seed

        # Add tools if provided (not supported for o1 models)
        if config.tools and not is_o1_model:
            payload["tools"] = self._format_tools(config.tools)

            if config.tool_choice:
                if config.tool_choice in ("auto", "required", "none"):
                    payload["tool_choice"] = config.tool_choice
                else:
                    # Specific tool name
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": config.tool_choice}
                    }

        # Add response format if specified
        if config.response_format:
            payload["response_format"] = config.response_format

        return payload

    def _format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure tools are in OpenAI format."""
        formatted_tools = []
        for tool in tools:
            if "function" in tool:
                # Already in OpenAI format
                formatted_tools.append(tool)
            else:
                # Convert from Anthropic/generic format
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", tool.get("parameters", {})),
                    }
                })
        return formatted_tools

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make the HTTP request to OpenAI's API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        if self.organization:
            headers["OpenAI-Organization"] = self.organization

        log.debug(f"OpenAI request: model={payload.get('model')}, max_tokens={payload.get('max_tokens')}")

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
        """Parse OpenAI's API response."""
        choices = response.get("choices", [])
        if not choices:
            raise ProviderError("No response choices returned")

        choice = choices[0]
        message = choice.get("message", {})

        text_content = message.get("content") or ""
        tool_calls = message.get("tool_calls")

        # Parse usage
        usage_data = response.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        # Map finish reason
        finish_reason = choice.get("finish_reason", "stop")

        latency_ms = (time.time() - start_time) * 1000

        return GenerationResult(
            content=text_content,
            usage=usage,
            model=response.get("model", model),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors from OpenAI's API."""
        status_code = error.response.status_code
        try:
            error_body = error.response.json()
            error_data = error_body.get("error", {})
            error_message = error_data.get("message", str(error))
            error_type = error_data.get("type", "")
        except Exception:
            error_message = str(error)
            error_type = ""

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
        elif status_code == 403:
            raise ProviderError(f"Access denied: {error_message}", retryable=False, status_code=403)
        elif status_code >= 500:
            raise ProviderError(f"Server error: {error_message}", retryable=True, status_code=status_code)
        else:
            raise ProviderError(f"API error ({status_code}): {error_message}", retryable=False, status_code=status_code)

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Estimate token count for text.

        For more accurate counts, consider using tiktoken library:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
