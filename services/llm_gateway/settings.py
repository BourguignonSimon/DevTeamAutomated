from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewaySettings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    provider_order: tuple[str, ...] = tuple(
        [p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "anthropic,openai,gemini").split(",") if p.strip()]
    )
    timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "20"))
    max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    cache_ttl_s: int = int(os.getenv("LLM_CACHE_TTL_S", "3600"))
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    test_mode: bool = os.getenv("LLM_TEST_MODE", "false").lower() in {"1", "true", "yes"}
