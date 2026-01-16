"""Local LLM provider implementation.

This module provides integration with local LLM servers including:
- Ollama
- LocalAI
- LMStudio
- vLLM
- Any OpenAI-compatible local server

Supports various open-source models like Llama, Mistral, Qwen, Phi, etc.
"""
from __future__ import annotations

import json
import logging
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from services.llm_gateway.providers.base import Provider, ProviderError

log = logging.getLogger(__name__)


class ServerType(str, Enum):
    """Supported local LLM server types."""
    OLLAMA = "ollama"
    LOCALAI = "localai"
    LMSTUDIO = "lmstudio"
    VLLM = "vllm"
    OPENAI_COMPATIBLE = "openai_compatible"


class LocalProvider(Provider):
    """Provider for local LLM servers.

    Supports Ollama, LocalAI, LMStudio, vLLM, and any OpenAI-compatible
    local server. Automatically adapts API format based on server type.
    """

    # Default ports for different server types
    DEFAULT_PORTS = {
        ServerType.OLLAMA: 11434,
        ServerType.LOCALAI: 8080,
        ServerType.LMSTUDIO: 1234,
        ServerType.VLLM: 8000,
        ServerType.OPENAI_COMPATIBLE: 8000,
    }

    def __init__(
        self,
        server_type: str | ServerType = ServerType.OLLAMA,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str = "llama3.1:8b",
        timeout_seconds: float = 300,  # Local models may be slower
        max_retries: int = 2,
    ) -> None:
        super().__init__("local")

        # Parse server type
        if isinstance(server_type, str):
            try:
                self.server_type = ServerType(server_type.lower())
            except ValueError:
                self.server_type = ServerType.OPENAI_COMPATIBLE
        else:
            self.server_type = server_type

        # Set base URL
        default_port = self.DEFAULT_PORTS.get(self.server_type, 8000)
        default_url = f"http://localhost:{default_port}"
        self.base_url = (base_url or os.getenv("LOCAL_LLM_URL", default_url)).rstrip("/")

        self.api_key = api_key or os.getenv("LOCAL_LLM_API_KEY")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers for local server."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_messages_ollama(self, prompt: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert prompt dict to Ollama messages format."""
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

                # Handle multimodal content
                if isinstance(content, list):
                    text_content = ""
                    images = []
                    for item in content:
                        if item.get("type") == "image":
                            images.append(item.get("data", ""))
                        elif item.get("type") == "text":
                            text_content += item.get("text", "")
                        else:
                            text_content += str(item)

                    msg_dict = {"role": role, "content": text_content}
                    if images:
                        msg_dict["images"] = images
                    messages.append(msg_dict)
                else:
                    messages.append({"role": role, "content": str(content)})
        else:
            # Build message from prompt fields
            content_parts = []

            if prompt.get("extracted_text"):
                content_parts.append(f"Extracted Text:\n{prompt['extracted_text']}")
            if prompt.get("extracted_table"):
                content_parts.append(f"Extracted Table:\n{prompt['extracted_table']}")
            if prompt.get("hints"):
                hints_str = json.dumps(prompt["hints"], indent=2)
                content_parts.append(f"Additional Context:\n{hints_str}")
            if prompt.get("query"):
                content_parts.append(f"Query:\n{prompt['query']}")
            elif prompt.get("prompt"):
                content_parts.append(prompt["prompt"])
            if prompt.get("instruction"):
                content_parts.append(f"Instruction:\n{prompt['instruction']}")

            messages.append({
                "role": "user",
                "content": "\n\n".join(content_parts) if content_parts else str(prompt),
            })

        return messages

    def _build_request_ollama(
        self,
        prompt: Dict[str, Any],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build Ollama API request body."""
        body: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages_ollama(prompt),
            "stream": False,
            "options": {
                "num_predict": prompt.get("max_tokens", max_tokens),
                "temperature": prompt.get("temperature", temperature),
            },
        }

        # Add tools if provided (Ollama supports function calling)
        prompt_tools = prompt.get("tools") or tools
        if prompt_tools:
            ollama_tools = []
            for tool in prompt_tools:
                if "function" in tool:
                    ollama_tools.append(tool)
                else:
                    ollama_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", tool.get("parameters", {})),
                        },
                    })
            body["tools"] = ollama_tools

        # Add stop sequences if provided
        if prompt.get("stop_sequences"):
            body["options"]["stop"] = prompt["stop_sequences"]

        # Add top_p if provided
        if prompt.get("top_p"):
            body["options"]["top_p"] = prompt["top_p"]

        # Add top_k if provided
        if prompt.get("top_k"):
            body["options"]["top_k"] = prompt["top_k"]

        # Add seed for reproducibility
        if prompt.get("seed"):
            body["options"]["seed"] = prompt["seed"]

        return body

    def _build_request_openai_compatible(
        self,
        prompt: Dict[str, Any],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Build OpenAI-compatible API request body."""
        messages: List[Dict[str, Any]] = []

        # Add system message if provided
        if prompt.get("system_prompt"):
            messages.append({
                "role": "system",
                "content": prompt["system_prompt"],
            })

        # Handle conversation history or build from prompt
        if "messages" in prompt:
            for msg in prompt["messages"]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Simplify multimodal content for local models
                    text_content = " ".join(
                        item.get("text", str(item)) for item in content
                        if item.get("type") != "image"
                    )
                    messages.append({"role": role, "content": text_content})
                else:
                    messages.append({"role": role, "content": str(content)})
        else:
            content_parts = []
            if prompt.get("extracted_text"):
                content_parts.append(f"Extracted Text:\n{prompt['extracted_text']}")
            if prompt.get("extracted_table"):
                content_parts.append(f"Extracted Table:\n{prompt['extracted_table']}")
            if prompt.get("hints"):
                hints_str = json.dumps(prompt["hints"], indent=2)
                content_parts.append(f"Additional Context:\n{hints_str}")
            if prompt.get("query"):
                content_parts.append(f"Query:\n{prompt['query']}")
            elif prompt.get("prompt"):
                content_parts.append(prompt["prompt"])
            if prompt.get("instruction"):
                content_parts.append(f"Instruction:\n{prompt['instruction']}")

            messages.append({
                "role": "user",
                "content": "\n\n".join(content_parts) if content_parts else str(prompt),
            })

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": prompt.get("max_tokens", max_tokens),
            "temperature": prompt.get("temperature", temperature),
        }

        # Add tools if provided
        prompt_tools = prompt.get("tools") or tools
        if prompt_tools:
            openai_tools = []
            for tool in prompt_tools:
                if "function" in tool:
                    openai_tools.append(tool)
                else:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", tool.get("parameters", {})),
                        },
                    })
            body["tools"] = openai_tools

        if prompt.get("stop_sequences"):
            body["stop"] = prompt["stop_sequences"]

        if prompt.get("top_p"):
            body["top_p"] = prompt["top_p"]

        return body

    def _get_endpoint(self) -> str:
        """Get the API endpoint based on server type."""
        if self.server_type == ServerType.OLLAMA:
            return f"{self.base_url}/api/chat"
        else:
            # OpenAI-compatible endpoint
            return f"{self.base_url}/v1/chat/completions"

    def predict(
        self,
        prompt: Dict[str, Any],
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Make a prediction using the local LLM server.

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
        # Add system prompt to prompt dict if provided
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        url = self._get_endpoint()
        headers = self._build_headers()

        # Build request based on server type
        if self.server_type == ServerType.OLLAMA:
            body = self._build_request_ollama(prompt, used_model, max_tokens, temperature, tools)
        else:
            body = self._build_request_openai_compatible(prompt, used_model, max_tokens, temperature, tools)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data, used_model)

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        wait_time = 2 ** attempt
                        log.warning(f"Server error {response.status_code}, waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue

                    # Client errors - don't retry
                    error_text = response.text
                    raise ProviderError(f"Local LLM API error ({response.status_code}): {error_text}")

            except httpx.ConnectError as e:
                last_error = e
                log.warning(f"Connection error on attempt {attempt + 1}/{self.max_retries}: {e}")
                log.warning(f"Is the local LLM server running at {self.base_url}?")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
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
        """Parse local LLM response into result and usage dicts."""
        if self.server_type == ServerType.OLLAMA:
            return self._parse_ollama_response(data, model)
        else:
            return self._parse_openai_compatible_response(data, model)

    def _parse_ollama_response(self, data: Dict[str, Any], model: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse Ollama API response."""
        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        # Try to parse JSON from content
        result_json: Dict[str, Any] = {}
        if content:
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
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
                func = tc.get("function", {})
                parsed_tool_calls.append({
                    "id": f"call_{len(parsed_tool_calls)}",
                    "name": func.get("name"),
                    "input": func.get("arguments", {}),
                })
            result_json["tool_use"] = parsed_tool_calls

        # Extract usage information
        usage = {
            "provider": "local",
            "server_type": self.server_type.value,
            "model": model,
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            "stop_reason": "stop" if data.get("done") else None,
            "total_duration_ns": data.get("total_duration"),
            "load_duration_ns": data.get("load_duration"),
            "eval_duration_ns": data.get("eval_duration"),
        }

        return result_json, usage

    def _parse_openai_compatible_response(self, data: Dict[str, Any], model: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Parse OpenAI-compatible API response."""
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
            "provider": "local",
            "server_type": self.server_type.value,
            "model": data.get("model", model),
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
            "stop_reason": choice.get("finish_reason"),
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
        """Async version of predict method."""
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        url = self._get_endpoint()
        headers = self._build_headers()

        if self.server_type == ServerType.OLLAMA:
            body = self._build_request_ollama(prompt, used_model, max_tokens, temperature, tools)
        else:
            body = self._build_request_openai_compatible(prompt, used_model, max_tokens, temperature, tools)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=body)

                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_response(data, used_model)

                    if response.status_code >= 500:
                        wait_time = 2 ** attempt
                        log.warning(f"Server error {response.status_code}, waiting {wait_time}s before retry")
                        import asyncio
                        await asyncio.sleep(wait_time)
                        continue

                    error_text = response.text
                    raise ProviderError(f"Local LLM API error ({response.status_code}): {error_text}")

            except httpx.ConnectError as e:
                last_error = e
                log.warning(f"Connection error on attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                continue
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
        """Stream responses from local LLM server.

        Yields:
            Dict containing partial response data

        Raises:
            ProviderError: If API call fails
        """
        if system_prompt and "system_prompt" not in prompt:
            prompt = {**prompt, "system_prompt": system_prompt}

        used_model = model or self.default_model
        headers = self._build_headers()

        if self.server_type == ServerType.OLLAMA:
            url = f"{self.base_url}/api/chat"
            body = self._build_request_ollama(prompt, used_model, max_tokens, temperature)
            body["stream"] = True
        else:
            url = f"{self.base_url}/v1/chat/completions"
            body = self._build_request_openai_compatible(prompt, used_model, max_tokens, temperature)
            body["stream"] = True

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code != 200:
                        error_text = ""
                        for chunk in response.iter_text():
                            error_text += chunk
                        raise ProviderError(f"Local LLM API error ({response.status_code}): {error_text}")

                    for line in response.iter_lines():
                        if not line:
                            continue
                        # Handle SSE format
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                yield data
                            except json.JSONDecodeError:
                                continue
                        else:
                            # Ollama streams raw JSON
                            try:
                                data = json.loads(line)
                                yield data
                            except json.JSONDecodeError:
                                continue

        except httpx.ConnectError:
            raise ProviderError(f"Cannot connect to local LLM server at {self.base_url}")
        except httpx.TimeoutException:
            raise ProviderError("Request timeout during streaming")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error during streaming: {e}")

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models on the local server.

        Returns:
            List of model information dicts

        Raises:
            ProviderError: If API call fails
        """
        if self.server_type == ServerType.OLLAMA:
            url = f"{self.base_url}/api/tags"
        else:
            url = f"{self.base_url}/v1/models"

        headers = self._build_headers()

        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    if self.server_type == ServerType.OLLAMA:
                        return data.get("models", [])
                    else:
                        return data.get("data", [])

                raise ProviderError(f"Failed to list models: {response.text}")

        except httpx.ConnectError:
            raise ProviderError(f"Cannot connect to local LLM server at {self.base_url}")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error: {e}")

    def pull_model(self, model_name: str) -> bool:
        """Pull/download a model (Ollama only).

        Args:
            model_name: Name of the model to pull

        Returns:
            True if successful

        Raises:
            ProviderError: If API call fails or not supported
        """
        if self.server_type != ServerType.OLLAMA:
            raise ProviderError("Model pulling is only supported for Ollama")

        url = f"{self.base_url}/api/pull"
        headers = self._build_headers()
        body = {"name": model_name, "stream": False}

        try:
            with httpx.Client(timeout=600) as client:  # 10 min timeout for downloads
                response = client.post(url, headers=headers, json=body)

                if response.status_code == 200:
                    log.info(f"Successfully pulled model: {model_name}")
                    return True

                raise ProviderError(f"Failed to pull model: {response.text}")

        except httpx.ConnectError:
            raise ProviderError(f"Cannot connect to Ollama server at {self.base_url}")
        except httpx.TimeoutException:
            raise ProviderError("Model pull timed out")
        except httpx.RequestError as e:
            raise ProviderError(f"Request error: {e}")

    def is_available(self) -> bool:
        """Check if the local LLM server is available.

        Returns:
            True if server is reachable
        """
        try:
            with httpx.Client(timeout=5) as client:
                if self.server_type == ServerType.OLLAMA:
                    response = client.get(f"{self.base_url}/api/tags")
                else:
                    response = client.get(f"{self.base_url}/v1/models", headers=self._build_headers())
                return response.status_code == 200
        except Exception:
            return False
