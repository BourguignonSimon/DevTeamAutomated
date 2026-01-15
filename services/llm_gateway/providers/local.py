"""Local LLM Provider for Ollama and LM Studio.

This module provides integration with local LLM servers like Ollama and LM Studio
that expose OpenAI-compatible APIs.
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

# Default endpoints for local providers
OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_OPENAI_URL = "http://localhost:11434/v1/chat/completions"
LM_STUDIO_API_URL = "http://localhost:1234/v1/chat/completions"
DEFAULT_MODEL = "llama3.2:latest"


class LocalProvider(Provider):
    """Provider for local LLM servers (Ollama, LM Studio, etc.).

    Supports local LLM servers that expose either:
    - Ollama native API
    - OpenAI-compatible API (Ollama /v1, LM Studio, LocalAI, etc.)

    Features supported:
    - Multi-turn conversations
    - System prompts
    - Tool/function calling (model dependent)
    - Streaming (optional)

    Note: Actual feature support depends on the local model being used.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,  # Usually not needed for local
        api_base_url: str = OLLAMA_OPENAI_URL,
        use_ollama_native: bool = False,
        timeout: float = 300.0,  # Longer timeout for local models
    ):
        super().__init__("local", api_key)
        self.api_base_url = api_base_url
        self.use_ollama_native = use_ollama_native
        self.timeout = timeout

        # Auto-detect if using Ollama native API
        if "11434/api" in api_base_url and "/v1" not in api_base_url:
            self.use_ollama_native = True

    def _get_default_model(self) -> str:
        return DEFAULT_MODEL

    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Generate a response using the local LLM server.

        Args:
            messages: List of conversation messages
            config: Generation configuration

        Returns:
            GenerationResult with the model's response
        """
        start_time = time.time()

        try:
            if self.use_ollama_native:
                return self._generate_ollama_native(messages, config, start_time)
            else:
                return self._generate_openai_compatible(messages, config, start_time)
        except httpx.ConnectError:
            raise ProviderError(
                f"Could not connect to local LLM server at {self.api_base_url}. "
                "Make sure Ollama or LM Studio is running.",
                retryable=True
            )
        except httpx.TimeoutException:
            raise ProviderError(f"Request timed out after {self.timeout}s", retryable=True)
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {str(e)}", retryable=True)

    def _generate_ollama_native(
        self,
        messages: List[Message],
        config: GenerationConfig,
        start_time: float,
    ) -> GenerationResult:
        """Generate using Ollama's native API format."""
        # Build Ollama-native payload
        ollama_messages = []

        # Add system prompt if provided
        if config.system_prompt:
            ollama_messages.append({
                "role": "system",
                "content": config.system_prompt,
            })

        for msg in messages:
            ollama_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": config.max_tokens,
            },
        }

        # Add optional parameters
        if config.temperature is not None:
            payload["options"]["temperature"] = config.temperature

        if config.top_p is not None:
            payload["options"]["top_p"] = config.top_p

        if config.stop_sequences:
            payload["options"]["stop"] = config.stop_sequences

        # Add tools if supported
        if config.tools:
            payload["tools"] = self._format_tools_ollama(config.tools)

        # Make request
        response = self._make_request(payload)

        # Parse Ollama native response
        message = response.get("message", {})
        text_content = message.get("content", "")

        # Handle tool calls
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = []
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": tc.get("function", {}).get("name"),
                        "arguments": json.dumps(tc.get("function", {}).get("arguments", {})),
                    },
                })

        # Parse usage (Ollama provides different metrics)
        usage = TokenUsage(
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            total_tokens=response.get("prompt_eval_count", 0) + response.get("eval_count", 0),
        )

        finish_reason = "tool_calls" if tool_calls else "stop"
        if response.get("done_reason") == "length":
            finish_reason = "length"

        latency_ms = (time.time() - start_time) * 1000

        return GenerationResult(
            content=text_content,
            usage=usage,
            model=response.get("model", config.model),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def _generate_openai_compatible(
        self,
        messages: List[Message],
        config: GenerationConfig,
        start_time: float,
    ) -> GenerationResult:
        """Generate using OpenAI-compatible API format."""
        # Build OpenAI-compatible payload
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

            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls

            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id

            openai_messages.append(openai_msg)

        payload: Dict[str, Any] = {
            "model": config.model,
            "messages": openai_messages,
            "max_tokens": config.max_tokens,
            "stream": False,
        }

        # Add optional parameters
        if config.temperature is not None:
            payload["temperature"] = config.temperature

        if config.top_p is not None:
            payload["top_p"] = config.top_p

        if config.stop_sequences:
            payload["stop"] = config.stop_sequences

        # Add tools if provided
        if config.tools:
            payload["tools"] = self._format_tools_openai(config.tools)

            if config.tool_choice:
                if config.tool_choice in ("auto", "required", "none"):
                    payload["tool_choice"] = config.tool_choice
                else:
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": config.tool_choice}
                    }

        # Make request
        response = self._make_request(payload)

        # Parse OpenAI-compatible response
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

        finish_reason = choice.get("finish_reason", "stop")

        latency_ms = (time.time() - start_time) * 1000

        return GenerationResult(
            content=text_content,
            usage=usage,
            model=response.get("model", config.model),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def _format_tools_ollama(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for Ollama native API."""
        ollama_tools = []
        for tool in tools:
            if "function" in tool:
                # OpenAI format
                ollama_tools.append({
                    "type": "function",
                    "function": tool["function"],
                })
            elif "input_schema" in tool:
                # Anthropic format
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                })
            else:
                ollama_tools.append(tool)
        return ollama_tools

    def _format_tools_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format tools for OpenAI-compatible API."""
        openai_tools = []
        for tool in tools:
            if "function" in tool:
                openai_tools.append(tool)
            elif "input_schema" in tool:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                })
            else:
                openai_tools.append({
                    "type": "function",
                    "function": tool,
                })
        return openai_tools

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make the HTTP request to the local server."""
        headers = {
            "Content-Type": "application/json",
        }

        # Add API key if provided (some local servers may require it)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        log.debug(f"Local LLM request: url={self.api_base_url}, model={payload.get('model')}")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.api_base_url,
                headers=headers,
                json=payload,
            )

            # Handle errors
            if response.status_code >= 400:
                self._handle_http_error(response)

            return response.json()

    def _handle_http_error(self, response: httpx.Response) -> None:
        """Handle HTTP errors from the local server."""
        status_code = response.status_code
        try:
            error_body = response.json()
            error_message = error_body.get("error", {})
            if isinstance(error_message, dict):
                error_message = error_message.get("message", str(error_body))
            else:
                error_message = str(error_message or error_body)
        except Exception:
            error_message = response.text or f"HTTP {status_code}"

        if status_code == 404:
            raise ModelNotFoundError(
                f"Model not found: {error_message}. "
                "Make sure the model is pulled (ollama pull <model>)"
            )
        elif status_code == 400:
            raise ProviderError(f"Bad request: {error_message}", retryable=False, status_code=400)
        elif status_code >= 500:
            raise ProviderError(f"Server error: {error_message}", retryable=True, status_code=status_code)
        else:
            raise ProviderError(f"API error ({status_code}): {error_message}", retryable=False, status_code=status_code)

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models on the local server (Ollama only)."""
        try:
            # Try Ollama tags endpoint
            base = self.api_base_url.split("/api")[0] if "/api" in self.api_base_url else self.api_base_url.rsplit("/v1", 1)[0]
            url = f"{base}/api/tags"

            with httpx.Client(timeout=10) as client:
                response = client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", [])
        except Exception as e:
            log.debug(f"Could not list models: {e}")

        return []

    def health_check(self) -> bool:
        """Check if the local LLM server is accessible."""
        try:
            # Try a simple request to check connectivity
            base = self.api_base_url.split("/api")[0] if "/api" in self.api_base_url else self.api_base_url.rsplit("/v1", 1)[0]

            with httpx.Client(timeout=5) as client:
                # Try Ollama health endpoint
                try:
                    response = client.get(f"{base}/")
                    if response.status_code == 200:
                        return True
                except Exception:
                    pass

                # Try OpenAI models endpoint
                try:
                    response = client.get(f"{base}/v1/models")
                    if response.status_code == 200:
                        return True
                except Exception:
                    pass

            return False
        except Exception as e:
            log.warning(f"Health check failed for local provider: {e}")
            return False

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Estimate token count for text.

        Note: This is a rough approximation. Actual tokenization
        depends on the specific model being used.
        """
        # Rough approximation: ~4 characters per token
        return len(text) // 4
