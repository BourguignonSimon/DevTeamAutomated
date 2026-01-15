"""Google Gemini LLM Provider.

This module provides integration with Google's Gemini API.
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

# Gemini API constants
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(Provider):
    """Provider for Google's Gemini API.

    Supports all Gemini models including Gemini 2.0 Flash, Gemini 1.5 Pro,
    and Gemini 1.5 Flash with full feature support including:
    - Multi-turn conversations
    - System instructions
    - Tool/function calling
    - Vision (image inputs)
    - JSON mode
    - Very large context windows (up to 2M tokens)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base_url: str = GEMINI_API_URL,
        timeout: float = 120.0,
    ):
        super().__init__("gemini", api_key)
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout

    def _get_default_model(self) -> str:
        return DEFAULT_MODEL

    def generate(
        self,
        messages: List[Message],
        config: GenerationConfig,
    ) -> GenerationResult:
        """Generate a response using Google's Gemini API.

        Args:
            messages: List of conversation messages
            config: Generation configuration

        Returns:
            GenerationResult with Gemini's response
        """
        if not self.api_key:
            raise AuthenticationError("Google API key is required")

        start_time = time.time()

        # Build request payload
        payload = self._build_request_payload(messages, config)

        # Build the API URL
        model = config.model
        url = f"{self.api_base_url}/{model}:generateContent?key={self.api_key}"

        # Make API request
        try:
            response = self._make_request(url, payload)
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
        # Convert messages to Gemini format
        gemini_contents = []
        system_instruction = config.system_prompt

        for msg in messages:
            if msg.role == "system":
                # Gemini uses systemInstruction parameter
                system_instruction = msg.content
                continue

            # Map roles
            role = "user" if msg.role == "user" else "model"

            gemini_content: Dict[str, Any] = {
                "role": role,
                "parts": [],
            }

            # Handle text content
            if msg.content:
                gemini_content["parts"].append({"text": msg.content})

            # Handle tool results
            if msg.tool_call_id and msg.role == "user":
                # In Gemini, tool results are sent as functionResponse
                try:
                    result_data = json.loads(msg.content)
                except (json.JSONDecodeError, TypeError):
                    result_data = {"result": msg.content}

                gemini_content["parts"] = [{
                    "functionResponse": {
                        "name": msg.name or "unknown",
                        "response": result_data,
                    }
                }]

            # Handle tool calls from assistant
            if msg.role == "assistant" and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    func = tool_call.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    gemini_content["parts"].append({
                        "functionCall": {
                            "name": func.get("name"),
                            "args": args,
                        }
                    })

            gemini_contents.append(gemini_content)

        payload: Dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "maxOutputTokens": config.max_tokens,
            },
        }

        # Add system instruction if provided
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Add generation config
        gen_config = payload["generationConfig"]

        if config.temperature is not None:
            gen_config["temperature"] = config.temperature

        if config.top_p is not None:
            gen_config["topP"] = config.top_p

        if config.stop_sequences:
            gen_config["stopSequences"] = config.stop_sequences

        # Add response format for JSON mode
        if config.response_format:
            if config.response_format.get("type") == "json_object":
                gen_config["responseMimeType"] = "application/json"
            elif config.response_format.get("json_schema"):
                gen_config["responseMimeType"] = "application/json"
                gen_config["responseSchema"] = config.response_format["json_schema"].get("schema", {})

        # Add tools if provided
        if config.tools:
            payload["tools"] = [{"functionDeclarations": self._convert_tools(config.tools)}]

            if config.tool_choice:
                tool_config: Dict[str, Any] = {}
                if config.tool_choice == "auto":
                    tool_config["functionCallingConfig"] = {"mode": "AUTO"}
                elif config.tool_choice == "required":
                    tool_config["functionCallingConfig"] = {"mode": "ANY"}
                elif config.tool_choice == "none":
                    tool_config["functionCallingConfig"] = {"mode": "NONE"}
                else:
                    # Specific tool name
                    tool_config["functionCallingConfig"] = {
                        "mode": "ANY",
                        "allowedFunctionNames": [config.tool_choice]
                    }
                payload["toolConfig"] = tool_config

        return payload

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to Gemini format."""
        gemini_tools = []
        for tool in tools:
            if "function" in tool:
                # OpenAI format - convert to Gemini format
                func = tool["function"]
                gemini_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                })
            elif "input_schema" in tool:
                # Anthropic format - convert to Gemini format
                gemini_tools.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                })
            else:
                # Already in Gemini format or generic
                gemini_tools.append(tool)
        return gemini_tools

    def _make_request(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make the HTTP request to Gemini's API."""
        headers = {
            "Content-Type": "application/json",
        }

        log.debug(f"Gemini request: url={url}, max_tokens={payload.get('generationConfig', {}).get('maxOutputTokens')}")

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                url,
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
        """Parse Gemini's API response."""
        candidates = response.get("candidates", [])
        if not candidates:
            # Check for blocked content
            prompt_feedback = response.get("promptFeedback", {})
            if prompt_feedback.get("blockReason"):
                raise ProviderError(
                    f"Content blocked: {prompt_feedback.get('blockReason')}",
                    retryable=False
                )
            raise ProviderError("No response candidates returned")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_content = ""
        tool_calls = []

        for part in parts:
            if "text" in part:
                text_content += part["text"]
            elif "functionCall" in part:
                func_call = part["functionCall"]
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": func_call.get("name"),
                        "arguments": json.dumps(func_call.get("args", {})),
                    },
                })

        # Parse usage
        usage_data = response.get("usageMetadata", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("promptTokenCount", 0),
            output_tokens=usage_data.get("candidatesTokenCount", 0),
            total_tokens=usage_data.get("totalTokenCount", 0),
        )

        # Map finish reason
        finish_reason_raw = candidate.get("finishReason", "STOP")
        finish_reason_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "stop",
        }
        finish_reason = finish_reason_map.get(finish_reason_raw, "stop")

        if tool_calls:
            finish_reason = "tool_calls"

        latency_ms = (time.time() - start_time) * 1000

        return GenerationResult(
            content=text_content,
            usage=usage,
            model=model,
            finish_reason=finish_reason,
            tool_calls=tool_calls if tool_calls else None,
            raw_response=response,
            latency_ms=latency_ms,
        )

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors from Gemini's API."""
        status_code = error.response.status_code
        try:
            error_body = error.response.json()
            error_data = error_body.get("error", {})
            error_message = error_data.get("message", str(error))
            error_status = error_data.get("status", "")
        except Exception:
            error_message = str(error)
            error_status = ""

        if status_code == 401 or status_code == 403:
            raise AuthenticationError(f"Invalid API key: {error_message}")
        elif status_code == 429:
            # Try to extract retry information
            retry_after = error.response.headers.get("retry-after")
            retry_seconds = float(retry_after) if retry_after else None
            raise RateLimitError(f"Rate limit exceeded: {error_message}", retry_after=retry_seconds)
        elif status_code == 404:
            raise ModelNotFoundError(f"Model not found: {error_message}")
        elif status_code == 400:
            if "INVALID_ARGUMENT" in error_message or error_status == "INVALID_ARGUMENT":
                raise ProviderError(f"Invalid request: {error_message}", retryable=False, status_code=400)
            raise ProviderError(f"Bad request: {error_message}", retryable=False, status_code=400)
        elif status_code >= 500:
            raise ProviderError(f"Server error: {error_message}", retryable=True, status_code=status_code)
        else:
            raise ProviderError(f"API error ({status_code}): {error_message}", retryable=False, status_code=status_code)

    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Estimate token count for text.

        Note: Gemini has a countTokens API that can be used for exact counts.
        This is a rough approximation.
        """
        # Rough approximation: ~4 characters per token
        return len(text) // 4
