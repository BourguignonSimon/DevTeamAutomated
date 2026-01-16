"""OpenAI GPT provider implementation.

This module provides full integration with OpenAI's API,
supporting GPT-4, GPT-3.5, and o1 models with proper error handling,
retries, and structured output support.
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


class OpenAIProvider(Provider):
    """Provider for OpenAI GPT models.

    Supports GPT-4o, GPT-4, GPT-3.5-turbo, and o1 models
    with vision capabilities, function calling, and structured outputs.
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        organization_id: str | None = None,
        default_model: str = "gpt-4o",
        timeout_seconds: float = 120,
        max_retries: int = 3,
    ) -> None:
        super().__init__("openai")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.organization_id = organization_id or os.getenv("OPENAI_ORG_ID")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers for OpenAI API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or ''}",
        }
        if self.organization_id:
            headers["OpenAI-Organization"] = self.organization_id
        return headers

    def _build_messages(self, prompt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert prompt dict to OpenAI messages format."""
        messages: List[Dict[str, Any]] = []

        # Add system message if provided
        if prompt.get("system_prompt"):
            messages.append({
                "role": "system",
                "content": prompt["system_prompt"],
            })

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
                            # Base64 image
                            formatted_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{item.get('media_type', 'image/png')};base64,{item.get('data', '')}",
                                    "detail": item.get("detail", "auto"),
                                },
                            })
                        elif item.get("type") == "image_url":
                            # URL-based image
                            formatted_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": item.get("url", ""),
                                    "detail": item.get("detail", "auto"),
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
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: str | Dict[str, Any] | None = None,
        response_format: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build the request body for OpenAI API."""
        used_model = model or self.default_model

        body: Dict[str, Any] = {
            "model": used_model,
            "messages": self._build_messages(prompt),
        }

        # o1 models have specific constraints
        is_o1_model = used_model.startswith("o1")

        if not is_o1_model:
            body["max_tokens"] = prompt.get("max_tokens", max_tokens)
            body["temperature"] = prompt.get("temperature", temperature)

            # Add tools if provided (not supported by o1)
            prompt_tools = prompt.get("tools") or tools
            if prompt_tools:
                # Convert to OpenAI function format
                openai_tools = []
                for tool in prompt_tools:
                    if "function" in tool:
                        openai_tools.append(tool)
                    else:
                        # Assume it's an Anthropic-style tool, convert
                        openai_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.get("name", ""),
                                "description": tool.get("description", ""),
                                "parameters": tool.get("input_schema", tool.get("parameters", {})),
                            },
                        })
                body["tools"] = openai_tools

                if prompt.get("tool_choice") or tool_choice:
                    body["tool_choice"] = prompt.get("tool_choice") or tool_choice

            # Add response format if provided
            if prompt.get("response_format") or response_format:
                body["response_format"] = prompt.get("response_format") or response_format
        else:
            # o1 models use max_completion_tokens
            body["max_completion_tokens"] = prompt.get("max_tokens", max_tokens)

        # Add stop sequences if provided
        if prompt.get("stop_sequences"):
            body["stop"] = prompt["stop_sequences"]

        # Add seed for reproducibility if provided
        if prompt.get("seed"):
            body["seed"] = prompt["seed"]

        # Add top_p if provided and not o1
        if not is_o1_model and prompt.get("top_p"):
            body["top_p"] = prompt["top_p"]

        # Add frequency/presence penalty if provided and not o1
        if not is_o1_model:
            if prompt.get("frequency_penalty"):
                body["frequency_penalty"] = prompt["frequency_penalty"]
            if prompt.get("presence_penalty"):
                body["presence_penalty"] = prompt["presence_penalty"]

        return body

    def predict(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: str | Dict[str, Any] | None = None,
        response_format: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the OpenAI API.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-2)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling
            tool_choice: Tool choice configuration
            response_format: Response format specification

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("OpenAI API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
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

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        wait_time = 2 ** attempt
                        log.warning(f"Server error {response.status_code}, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue

                    # Client errors - don't retry
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_message = error_data.get("error", {}).get("message", response.text)
                    raise ProviderError(f"OpenAI API error ({response.status_code}): {error_message}")

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
        """Parse OpenAI API response into result and usage dicts."""
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError("No choices in response")

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        # Try to parse JSON from content
        result_json: Dict[str, Any] = {}
        if content:
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
                # Try to find JSON in the text
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    try:
                        result_json = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result_json = {"text": content}
                else:
                    result_json = {"text": content}

        # Add tool calls if present
        if tool_calls:
            parsed_tool_calls = []
            for tc in tool_calls:
                parsed_tool_calls.append({
                    "id": tc.get("id"),
                    "name": tc.get("function", {}).get("name"),
                    "input": json.loads(tc.get("function", {}).get("arguments", "{}")),
                })
            result_json["tool_use"] = parsed_tool_calls

        # Extract usage information
        usage_data = data.get("usage", {})
        usage = {
            "provider": "openai",
            "model": data.get("model", self.default_model),
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
            "stop_reason": choice.get("finish_reason"),
        }

        # Add reasoning tokens for o1 models
        if usage_data.get("completion_tokens_details"):
            details = usage_data["completion_tokens_details"]
            if details.get("reasoning_tokens"):
                usage["reasoning_tokens"] = details["reasoning_tokens"]

        return result_json, usage

    async def predict_async(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        tool_choice: str | Dict[str, Any] | None = None,
        response_format: Dict[str, Any] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Async version of predict method.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-2)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling
            tool_choice: Tool choice configuration
            response_format: Response format specification

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("OpenAI API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
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
                    raise ProviderError(f"OpenAI API error ({response.status_code}): {error_message}")

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
        """Stream responses from OpenAI API.

        Yields:
            Dict containing partial response data

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("OpenAI API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        body = self._build_request_body(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        body["stream"] = True

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code != 200:
                        error_text = ""
                        for chunk in response.iter_text():
                            error_text += chunk
                        raise ProviderError(f"OpenAI API error ({response.status_code}): {error_text}")

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

    def create_embedding(
        self,
        text: str | List[str],
        model: str = "text-embedding-3-small",
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Create embeddings using OpenAI API.

        Args:
            text: Text or list of texts to embed
            model: Embedding model to use

        Returns:
            Tuple of (embeddings list, usage dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("OpenAI API key is required")

        url = f"{self.base_url}/embeddings"
        headers = self._build_headers()
        body = {
            "model": model,
            "input": text if isinstance(text, list) else [text],
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=body)

                if response.status_code == 200:
                    data = response.json()
                    embeddings = [item["embedding"] for item in data.get("data", [])]
                    usage = {
                        "provider": "openai",
                        "model": model,
                        "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                    }
                    return embeddings, usage

                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_message = error_data.get("error", {}).get("message", response.text)
                raise ProviderError(f"OpenAI API error ({response.status_code}): {error_message}")

        except httpx.TimeoutException:
            raise ProviderError("Request timeout during embedding creation")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error during embedding creation: {e}")
