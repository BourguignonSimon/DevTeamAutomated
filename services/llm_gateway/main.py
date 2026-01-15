"""LLM Gateway Service.

This service provides a unified API for multiple LLM providers (Anthropic, OpenAI,
Google Gemini, Local) with automatic fallback and retry logic.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from core.schema_registry import load_registry
from core.schema_validate import validate_payload
from services.llm_gateway.models import ExtractionRequest, ExtractionResponse
from services.llm_gateway.providers import (
    AnthropicProvider,
    GeminiProvider,
    LocalProvider,
    OpenAIProvider,
    Provider,
    ProviderError,
    RateLimitError,
)
from services.llm_gateway.providers.fake import FakeProvider
from services.llm_gateway.settings import GatewaySettings

log = logging.getLogger(__name__)


def build_providers(settings: GatewaySettings) -> Dict[str, Provider]:
    """Build provider instances based on settings.

    Args:
        settings: Gateway settings

    Returns:
        Dictionary of provider name to provider instance
    """
    providers: Dict[str, Provider] = {}

    # Anthropic provider
    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            api_key=settings.anthropic_api_key,
            timeout=settings.timeout_s,
        )
    else:
        log.warning("Anthropic API key not configured, provider unavailable")

    # OpenAI provider
    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(
            api_key=settings.openai_api_key,
            timeout=settings.timeout_s,
        )
    else:
        log.warning("OpenAI API key not configured, provider unavailable")

    # Google Gemini provider
    if settings.gemini_api_key:
        providers["google"] = GeminiProvider(
            api_key=settings.gemini_api_key,
            timeout=settings.timeout_s,
        )
        # Alias for compatibility
        providers["gemini"] = providers["google"]
    else:
        log.warning("Google/Gemini API key not configured, provider unavailable")

    # Local provider (always available, may fail at runtime)
    providers["local"] = LocalProvider(
        api_base_url=settings.local_api_url,
        timeout=settings.timeout_s,
    )

    # Fake provider for testing
    providers["fake"] = FakeProvider()

    return providers


def create_app(settings: Optional[GatewaySettings] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional gateway settings

    Returns:
        Configured FastAPI app
    """
    settings = settings or GatewaySettings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app = FastAPI(
        title="LLM Gateway",
        description="Multi-provider LLM gateway with automatic fallback",
        version="1.0.0",
    )

    # Load schema registry
    try:
        registry = load_registry("/app/schemas")
    except Exception as e:
        log.warning(f"Could not load schema registry: {e}")
        registry = None

    # Build providers
    providers = build_providers(settings)

    # Use fake provider in test mode
    if settings.test_mode:
        log.info("Running in test mode with fake provider")

    @app.get("/health")
    def health() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/providers")
    def list_providers() -> Dict[str, Any]:
        """List available providers and their status."""
        available = []
        for name in settings.provider_order:
            if name in providers:
                provider = providers[name]
                available.append({
                    "name": name,
                    "configured": True,
                    "default_model": settings.get_default_model(name),
                })

        return {
            "providers": available,
            "default_order": list(settings.provider_order),
            "test_mode": settings.test_mode,
        }

    def _validate_result(result_json: Dict[str, Any], schema_name: str) -> bool:
        """Validate result against schema."""
        if not registry:
            return True

        schema = registry.objects.get(schema_name)
        if not schema:
            raise HTTPException(status_code=400, detail=f"unknown schema {schema_name}")

        res = validate_payload(registry, schema.get("x_event_type", schema_name), result_json)
        return res.ok

    def _validate_object(result_json: Dict[str, Any], schema_name: str) -> bool:
        """Validate object against JSON schema."""
        if not registry:
            return True

        schema = registry.objects.get(schema_name)
        if not schema:
            return False

        from jsonschema import Draft202012Validator, RefResolver
        validator = Draft202012Validator(
            schema,
            resolver=RefResolver.from_schema(schema, store=registry.objects_by_id)
        )
        errors = list(validator.iter_errors(result_json))
        return not errors

    @app.post("/v1/extract/order", response_model=ExtractionResponse)
    def extract(req: ExtractionRequest) -> ExtractionResponse:
        """Extract structured data from text using LLM.

        This endpoint:
        1. Tries providers in order of preference
        2. Validates output against the specified schema
        3. Returns the first successful result or error

        Args:
            req: Extraction request

        Returns:
            Extraction response with results or error
        """
        # Determine provider order
        provider_order: List[str] = req.provider_preference or list(settings.provider_order)
        provider_order = [p for p in provider_order if p]

        # Use fake provider in test mode
        if settings.test_mode:
            provider_order = ["fake"]

        used_provider: Optional[str] = None
        warnings: List[str] = []
        last_error: Optional[Dict[str, Any]] = None

        # Build prompt
        prompt = {
            "extracted_text": req.input.extracted_text,
            "extracted_table": req.input.extracted_table,
            **req.input.hints,
        }
        prompt.setdefault("order_id", req.input.hints.get("order_id") if req.input.hints else None)

        for provider_name in provider_order:
            provider = providers.get(provider_name)
            if not provider:
                warnings.append(f"provider {provider_name} unavailable")
                continue

            for attempt in range(settings.max_retries + 1):
                try:
                    result_json, usage = provider.predict(prompt)

                    # Validate against schema
                    if not _validate_object(result_json, req.output_schema_name):
                        raise ProviderError("schema validation failed")

                    used_provider = provider_name
                    return ExtractionResponse(
                        ok=True,
                        provider_used=used_provider,
                        result_json=result_json,
                        usage=usage,
                        warnings=warnings,
                    )

                except RateLimitError as exc:
                    wait_time = exc.retry_after or (settings.retry_backoff ** attempt)
                    log.warning(f"Rate limit hit for {provider_name}, waiting {wait_time}s")
                    warnings.append(f"{provider_name}: rate limit, retrying")
                    time.sleep(min(wait_time, settings.timeout_s / 10))
                    continue

                except ProviderError as exc:
                    last_error = {"type": "provider_error", "message": str(exc)}
                    warnings.append(str(exc))
                    if exc.retryable:
                        time.sleep(settings.retry_backoff ** attempt)
                        continue
                    break

                except Exception as exc:
                    last_error = {"type": "exception", "message": str(exc)}
                    warnings.append(str(exc))
                    continue

        return ExtractionResponse(
            ok=False,
            provider_used=used_provider,
            result_json=None,
            warnings=warnings,
            error=last_error or {"type": "unavailable", "message": "no provider succeeded"},
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = GatewaySettings()
    uvicorn.run(app, host=settings.host, port=settings.port)
