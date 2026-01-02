from __future__ import annotations

from typing import Any, Dict, Tuple

from services.llm_gateway.providers.base import Provider, ProviderError


class OpenAIProvider(Provider):
    def __init__(self, api_key: str | None) -> None:
        super().__init__("openai")
        self.api_key = api_key

    def predict(self, prompt: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if not self.api_key:
            raise ProviderError("openai api key missing")
        raise ProviderError("openai provider not implemented in test mode")
