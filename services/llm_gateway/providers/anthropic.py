"""Anthropic Claude provider implementation.

This module provides full integration with Anthropic's Claude API,
supporting all Claude 3.x models with proper error handling, retries,
and structured output support.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from services.llm_gateway.providers.base import Provider, ProviderError

log = logging.getLogger(__name__)


class AnthropicProvider(Provider):
    """Provider for Anthropic Claude models.

    Supports Claude 3.5 Sonnet, Claude 3 Opus, Sonnet, and Haiku models
    with vision capabilities, tool use, and structured outputs.
    """

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        default_model: str = "claude-3-5-sonnet-20241022",
        timeout_seconds: float = 120,
        max_retries: int = 3,
    ) -> None:
        super().__init__("anthropic")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.api_version = api_version or os.getenv("ANTHROPIC_API_VERSION", self.DEFAULT_API_VERSION)
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers for Anthropic API."""
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": self.api_version,
        }

    def _build_messages(self, prompt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert prompt dict to Anthropic messages format."""
        messages: List[Dict[str, Any]] = []

        # Handle conversation history if provided
        if "messages" in prompt:
            for msg in prompt["messages"]:
                role = msg.get("role", "user")
                content = msg.get("content", "")

                # Handle multimodal content (images)
                if isinstance(content, list):
                    formatted_content = []
                    for item in content:
                        if item.get("type") == "image":
                            formatted_content.append({
                                "type": "image",
                                "source": {
                                    "type": item.get("source_type", "base64"),
                                    "media_type": item.get("media_type", "image/png"),
                                    "data": item.get("data", ""),
                                },
                            })
                        elif item.get("type") == "image_url":
                            # Handle URL-based images
                            formatted_content.append({
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": item.get("url", ""),
                                },
                            })
                        else:
                            formatted_content.append({
                                "type": "text",
                                "text": item.get("text", str(item)),
                            })
                    messages.append({"role": role, "content": formatted_content})
                else:
                    messages.append({"role": role, "content": str(content)})
        else:
            # Build message from prompt fields
            content_parts = []

            # Add extracted text if present
            if prompt.get("extracted_text"):
                content_parts.append(f"Extracted Text:\n{prompt['extracted_text']}")

            # Add extracted table if present
            if prompt.get("extracted_table"):
                content_parts.append(f"Extracted Table:\n{prompt['extracted_table']}")

            # Add any hints as context
            if prompt.get("hints"):
                hints_str = json.dumps(prompt["hints"], indent=2)
                content_parts.append(f"Additional Context:\n{hints_str}")

            # Add main prompt/query if present
            if prompt.get("query"):
                content_parts.append(f"Query:\n{prompt['query']}")
            elif prompt.get("prompt"):
                content_parts.append(prompt["prompt"])

            # Add instruction if present
            if prompt.get("instruction"):
                content_parts.append(f"Instruction:\n{prompt['instruction']}")

            messages.append({
                "role": "user",
                "content": "\n\n".join(content_parts) if content_parts else str(prompt),
            })

        return messages

    def _build_request_body(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build the request body for Anthropic API."""
        body: Dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": prompt.get("max_tokens", max_tokens),
            "temperature": prompt.get("temperature", temperature),
            "messages": self._build_messages(prompt),
        }

        # Add system prompt if provided
        system = prompt.get("system_prompt") or system_prompt
        if system:
            body["system"] = system

        # Add tools if provided
        prompt_tools = prompt.get("tools") or tools
        if prompt_tools:
            body["tools"] = prompt_tools
            if prompt.get("tool_choice") or tool_choice:
                body["tool_choice"] = prompt.get("tool_choice") or tool_choice

        # Add stop sequences if provided
        if prompt.get("stop_sequences"):
            body["stop_sequences"] = prompt["stop_sequences"]

        # Add metadata if provided
        if prompt.get("metadata"):
            body["metadata"] = prompt["metadata"]

        return body

    def predict(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the Anthropic API.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling
            tool_choice: Tool choice configuration

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Anthropic API key is required")

        url = f"{self.base_url}/v1/messages"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data)

                    # Handle rate limiting with exponential backoff
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("retry-after", 2 ** attempt))
                        log.warning(f"Rate limited, waiting {retry_after}s before retry")
                        time.sleep(retry_after)
                        continue

                    # Handle overloaded API
                    if response.status_code == 529:
                        wait_time = 2 ** attempt
                        log.warning(f"API overloaded, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        wait_time = 2 ** attempt
                        log.warning(f"Server error {response.status_code}, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue

                    # Client errors - don't retry
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_message = error_data.get("error", {}).get("message", response.text)
                    raise ProviderError(f"Anthropic API error ({response.status_code}): {error_message}")

            except httpx.TimeoutException as e:
                last_error = e
                log.warning(f"Request timeout on attempt {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            except httpx.RequestError as e:
                last_error = e
                log.warning(f"Request error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            except ProviderError:
                raise
            except Exception as e:
                last_error = e
                log.error(f"Unexpected error: {e}")
                raise ProviderError(f"Unexpected error: {e}")

        raise ProviderError(f"Max retries exceeded: {last_error}")

    def _parse_response(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse Anthropic API response into result and usage dicts."""
        # Extract content from response
        content_blocks = data.get("content", [])
        text_content = ""
        tool_use = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_use.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })

        # Try to parse JSON from text content
        result_json: Dict[str, Any] = {}
        if text_content:
            # Try to extract JSON from the response
            try:
                # First try direct JSON parse
                result_json = json.loads(text_content)
            except json.JSONDecodeError:
                # Try to find JSON in the text
                import re
                json_match = re.search(r'\{[\s\S]*\}', text_content)
                if json_match:
                    try:
                        result_json = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result_json = {"text": text_content}
                else:
                    result_json = {"text": text_content}

        # Add tool use if present
        if tool_use:
            result_json["tool_use"] = tool_use

        # Extract usage information
        usage_data = data.get("usage", {})
        usage = {
            "provider": "anthropic",
            "model": data.get("model", self.default_model),
            "input_tokens": usage_data.get("input_tokens", 0),
            "output_tokens": usage_data.get("output_tokens", 0),
            "total_tokens": usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            "stop_reason": data.get("stop_reason"),
        }

        return result_json, usage

    async def predict_async(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Async version of predict method.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling
            tool_choice: Tool choice configuration

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Anthropic API key is required")

        url = f"{self.base_url}/v1/messages"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data)

                    # Handle rate limiting with exponential backoff
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("retry-after", 2 ** attempt))
                        log.warning(f"Rate limited, waiting {retry_after}s before retry")
                        import asyncio
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle overloaded API
                    if response.status_code == 529:
                        wait_time = 2 ** attempt
                        log.warning(f"API overloaded, waiting {wait_time}s before retry")
                        import asyncio
                        await asyncio.sleep(wait_time)
                        continue

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        wait_time = 2 ** attempt
                        log.warning(f"Server error {response.status_code}, waiting {wait_time}s before retry")
                        import asyncio
                        await asyncio.sleep(wait_time)
                        continue

                    # Client errors - don't retry
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_message = error_data.get("error", {}).get("message", response.text)
                    raise ProviderError(f"Anthropic API error ({response.status_code}): {error_message}")

            except httpx.TimeoutException as e:
                last_error = e
                log.warning(f"Request timeout on attempt {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                continue
            except httpx.RequestError as e:
                last_error = e
                log.warning(f"Request error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                continue
            except ProviderError:
                raise
            except Exception as e:
                last_error = e
                log.error(f"Unexpected error: {e}")
                raise ProviderError(f"Unexpected error: {e}")

        raise ProviderError(f"Max retries exceeded: {last_error}")

    def stream(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ):
        """Stream responses from Anthropic API.

        Yields:
            Dict containing partial response data

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Anthropic API key is required")

        url = f"{self.base_url}/v1/messages"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        body["stream"] = True

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code != 200:
                        error_text = ""
                        for chunk in response.iter_text():
                            error_text += chunk
                        raise ProviderError(f"Anthropic API error ({response.status_code}): {error_text}")

                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                yield data
                            except json.JSONDecodeError:
                                continue

        except httpx.TimeoutException:
            raise ProviderError("Request timeout during streaming")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error during streaming: {e}")
