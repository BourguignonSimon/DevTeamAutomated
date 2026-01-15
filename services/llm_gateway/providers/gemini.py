"""Google Gemini provider implementation.

This module provides full integration with Google's Gemini API,
supporting Gemini Pro, Gemini Flash, and vision models with proper
error handling, retries, and structured output support.
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


class GeminiProvider(Provider):
    """Provider for Google Gemini models.

    Supports Gemini 1.5 Pro, Gemini 1.5 Flash, Gemini 2.0, and other models
    with vision capabilities, function calling, and structured outputs.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    # Safety settings mapping
    SAFETY_LEVELS = {
        "BLOCK_NONE": "BLOCK_NONE",
        "BLOCK_LOW_AND_ABOVE": "BLOCK_LOW_AND_ABOVE",
        "BLOCK_MEDIUM_AND_ABOVE": "BLOCK_MEDIUM_AND_ABOVE",
        "BLOCK_ONLY_HIGH": "BLOCK_ONLY_HIGH",
    }

    HARM_CATEGORIES = [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "gemini-1.5-pro",
        timeout_seconds: float = 120,
        max_retries: int = 3,
        safety_settings: Dict[str, str] | None = None,
    ) -> None:
        super().__init__("google")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.base_url = (base_url or os.getenv("GEMINI_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.safety_settings = safety_settings or {}

    def _build_safety_settings(self) -> List[Dict[str, str]]:
        """Build safety settings for Gemini API."""
        settings = []
        default_level = "BLOCK_MEDIUM_AND_ABOVE"

        for category in self.HARM_CATEGORIES:
            # Get setting from config or use default
            category_key = category.replace("HARM_CATEGORY_", "").lower()
            level = self.safety_settings.get(category_key, default_level)
            settings.append({
                "category": category,
                "threshold": level,
            })

        return settings

    def _build_contents(self, prompt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert prompt dict to Gemini contents format."""
        contents: List[Dict[str, Any]] = []

        # Handle conversation history if provided
        if "messages" in prompt:
            for msg in prompt["messages"]:
                role = msg.get("role", "user")
                # Gemini uses "user" and "model" roles
                gemini_role = "model" if role == "assistant" else "user"
                content = msg.get("content", "")

                parts: List[Dict[str, Any]] = []

                # Handle multimodal content
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "image":
                            # Base64 image
                            parts.append({
                                "inline_data": {
                                    "mime_type": item.get("media_type", "image/png"),
                                    "data": item.get("data", ""),
                                },
                            })
                        elif item.get("type") == "image_url":
                            # URL-based image - Gemini prefers inline data
                            # In a real implementation, you'd fetch and encode the image
                            parts.append({
                                "text": f"[Image URL: {item.get('url', '')}]",
                            })
                        else:
                            parts.append({
                                "text": item.get("text", str(item)),
                            })
                else:
                    parts.append({"text": str(content)})

                contents.append({
                    "role": gemini_role,
                    "parts": parts,
                })
        else:
            # Build content from prompt fields
            text_parts = []

            # Add extracted text if present
            if prompt.get("extracted_text"):
                text_parts.append(f"Extracted Text:\n{prompt['extracted_text']}")

            # Add extracted table if present
            if prompt.get("extracted_table"):
                text_parts.append(f"Extracted Table:\n{prompt['extracted_table']}")

            # Add any hints as context
            if prompt.get("hints"):
                hints_str = json.dumps(prompt["hints"], indent=2)
                text_parts.append(f"Additional Context:\n{hints_str}")

            # Add main prompt/query if present
            if prompt.get("query"):
                text_parts.append(f"Query:\n{prompt['query']}")
            elif prompt.get("prompt"):
                text_parts.append(prompt["prompt"])

            # Add instruction if present
            if prompt.get("instruction"):
                text_parts.append(f"Instruction:\n{prompt['instruction']}")

            contents.append({
                "role": "user",
                "parts": [{"text": "\n\n".join(text_parts) if text_parts else str(prompt)}],
            })

        return contents

    def _build_tools(self, tools: List[Dict[str, Any]] | None) -> List[Dict[str, Any]] | None:
        """Convert tools to Gemini function declarations format."""
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            # Handle different tool formats (Anthropic, OpenAI, Gemini native)
            if "function_declarations" in tool:
                function_declarations.extend(tool["function_declarations"])
            elif "function" in tool:
                # OpenAI format
                func = tool["function"]
                function_declarations.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })
            else:
                # Anthropic format
                function_declarations.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", tool.get("parameters", {})),
                })

        return [{"function_declarations": function_declarations}]

    def _build_request_body(
        self,
        prompt: Dict[str, Any],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build the request body for Gemini API."""
        body: Dict[str, Any] = {
            "contents": self._build_contents(prompt),
            "generationConfig": {
                "maxOutputTokens": prompt.get("max_tokens", max_tokens),
                "temperature": prompt.get("temperature", temperature),
            },
            "safetySettings": self._build_safety_settings(),
        }

        # Add system instruction if provided
        if prompt.get("system_prompt"):
            body["systemInstruction"] = {
                "parts": [{"text": prompt["system_prompt"]}],
            }

        # Add tools if provided
        prompt_tools = prompt.get("tools") or tools
        if prompt_tools:
            gemini_tools = self._build_tools(prompt_tools)
            if gemini_tools:
                body["tools"] = gemini_tools

        # Add stop sequences if provided
        if prompt.get("stop_sequences"):
            body["generationConfig"]["stopSequences"] = prompt["stop_sequences"]

        # Add top_p if provided
        if prompt.get("top_p"):
            body["generationConfig"]["topP"] = prompt["top_p"]

        # Add top_k if provided
        if prompt.get("top_k"):
            body["generationConfig"]["topK"] = prompt["top_k"]

        return body

    def predict(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the Gemini API.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Gemini API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        url = f"{self.base_url}/models/{used_model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = self._build_request_body(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data, used_model)

                    # Handle rate limiting with exponential backoff
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("retry-after", 2 ** attempt))
                        log.warning(f"Rate limited, waiting {retry_after}s before retry")
                        time.sleep(retry_after)
                        continue

                    # Handle resource exhausted
                    if response.status_code == 503:
                        wait_time = 2 ** attempt
                        log.warning(f"Service unavailable, waiting {wait_time}s before retry")
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
                    raise ProviderError(f"Gemini API error ({response.status_code}): {error_message}")

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

    def _parse_response(self, data: Dict[str, Any], model: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse Gemini API response into result and usage dicts."""
        candidates = data.get("candidates", [])
        if not candidates:
            # Check for blocked content
            if data.get("promptFeedback", {}).get("blockReason"):
                raise ProviderError(f"Content blocked: {data['promptFeedback']['blockReason']}")
            raise ProviderError("No candidates in response")

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_content = ""
        function_calls = []

        for part in parts:
            if "text" in part:
                text_content += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                function_calls.append({
                    "id": f"call_{len(function_calls)}",
                    "name": fc.get("name"),
                    "input": fc.get("args", {}),
                })

        # Try to parse JSON from text content
        result_json: Dict[str, Any] = {}
        if text_content:
            try:
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

        # Add function calls if present
        if function_calls:
            result_json["tool_use"] = function_calls

        # Extract usage information
        usage_data = data.get("usageMetadata", {})
        usage = {
            "provider": "google",
            "model": model,
            "input_tokens": usage_data.get("promptTokenCount", 0),
            "output_tokens": usage_data.get("candidatesTokenCount", 0),
            "total_tokens": usage_data.get("totalTokenCount", 0),
            "stop_reason": candidate.get("finishReason"),
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
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Async version of predict method.

        Args:
            prompt: The prompt dictionary containing input data
            model: Model to use (defaults to instance default_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            system_prompt: System prompt for context
            tools: List of tool definitions for function calling

        Returns:
            Tuple of (result_dict, usage_dict)

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Gemini API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        url = f"{self.base_url}/models/{used_model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = self._build_request_body(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data, used_model)

                    # Handle rate limiting with exponential backoff
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("retry-after", 2 ** attempt))
                        log.warning(f"Rate limited, waiting {retry_after}s before retry")
                        import asyncio
                        await asyncio.sleep(retry_after)
                        continue

                    # Handle resource exhausted
                    if response.status_code == 503:
                        wait_time = 2 ** attempt
                        log.warning(f"Service unavailable, waiting {wait_time}s before retry")
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
                    raise ProviderError(f"Gemini API error ({response.status_code}): {error_message}")

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
        """Stream responses from Gemini API.

        Yields:
            Dict containing partial response data

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Gemini API key is required")

        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        url = f"{self.base_url}/models/{used_model}:streamGenerateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = self._build_request_body(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code != 200:
                        error_text = ""
                        for chunk in response.iter_text():
                            error_text += chunk
                        raise ProviderError(f"Gemini API error ({response.status_code}): {error_text}")

                    buffer = ""
                    for chunk in response.iter_text():
                        buffer += chunk
                        # Gemini streams as newline-delimited JSON
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if line:
                                try:
                                    data = json.loads(line)
                                    yield data
                                except json.JSONDecodeError:
                                    continue

        except httpx.TimeoutException:
            raise ProviderError("Request timeout during streaming")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error during streaming: {e}")

    def count_tokens(
        self,
        text: str,
        model: str | None = None,
    ) -> int:
        """Count tokens for given text using Gemini API.

        Args:
            text: Text to count tokens for
            model: Model to use for tokenization

        Returns:
            Token count

        Raises:
            ProviderError: If API call fails
        """
        if not self.api_key:
            raise ProviderError("Gemini API key is required")

        used_model = model or self.default_model
        url = f"{self.base_url}/models/{used_model}:countTokens?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{"parts": [{"text": text}]}],
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=body)

                if response.status_code == 200:
                    data = response.json()
                    return data.get("totalTokens", 0)

                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_message = error_data.get("error", {}).get("message", response.text)
                raise ProviderError(f"Gemini API error ({response.status_code}): {error_message}")

        except httpx.TimeoutException:
            raise ProviderError("Request timeout during token counting")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error during token counting: {e}")
