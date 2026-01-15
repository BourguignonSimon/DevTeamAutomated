"""LLM Gateway Service.

This service provides a unified API for interacting with multiple
LLM providers (Anthropic, OpenAI, Google Gemini, Local LLMs).

Endpoints:
    GET /health - Health check
    GET /v1/providers - List available providers
    POST /v1/extract/order - Extract structured data from text (legacy)
    POST /v1/predict - General prediction endpoint
    POST /v1/chat - Chat completion endpoint
    GET /v1/usage - Get usage statistics
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.llm_client import LLMClient
from core.schema_registry import load_registry
from core.schema_validate import validate_payload
from services.llm_gateway.models import ExtractionRequest, ExtractionResponse
from services.llm_gateway.providers.anthropic import AnthropicProvider
from services.llm_gateway.providers.base import Provider, ProviderError
from services.llm_gateway.providers.fake import FakeProvider
from services.llm_gateway.providers.gemini import GeminiProvider
from services.llm_gateway.providers.local import LocalProvider
from services.llm_gateway.providers.openai import OpenAIProvider
from services.llm_gateway.settings import GatewaySettings

log = logging.getLogger(__name__)


# Request/Response models for new endpoints
class PredictRequest(BaseModel):
    """Request model for prediction endpoint."""
    prompt: str | Dict[str, Any]
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    agent_name: Optional[str] = None
    task_type: Optional[str] = None


class PredictResponse(BaseModel):
    """Response model for prediction endpoint."""
    ok: bool
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str
    content: str | List[Dict[str, Any]]


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    messages: List[ChatMessage]
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    agent_name: Optional[str] = None
    task_type: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    ok: bool
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


def build_providers(settings: GatewaySettings) -> Dict[str, Provider]:
    """Build provider instances from settings.

    Args:
        settings: Gateway settings

    Returns:
        Dictionary of provider instances
    """
    providers: Dict[str, Provider] = {}

    # Build Anthropic provider
    if settings.anthropic_api_key or settings.test_mode:
        providers["anthropic"] = AnthropicProvider(
            api_key=settings.anthropic_api_key,
            timeout_seconds=settings.timeout_s,
            max_retries=settings.max_retries,
        )

    # Build OpenAI provider
    if settings.openai_api_key or settings.test_mode:
        providers["openai"] = OpenAIProvider(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.timeout_s,
            max_retries=settings.max_retries,
        )

    # Build Gemini provider
    if settings.gemini_api_key or settings.test_mode:
        providers["google"] = GeminiProvider(
            api_key=settings.gemini_api_key,
            timeout_seconds=settings.timeout_s,
            max_retries=settings.max_retries,
        )
        # Alias for backwards compatibility
        providers["gemini"] = providers["google"]

    # Build Local provider (always available)
    providers["local"] = LocalProvider(
        base_url=settings.local_llm_url,
        timeout_seconds=settings.timeout_s,
        max_retries=settings.max_retries,
    )

    # Fake provider for testing
    providers["fake"] = FakeProvider()

    return providers


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        settings: Optional gateway settings

    Returns:
        FastAPI application instance
    """
    settings = settings or GatewaySettings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app = FastAPI(
        title="LLM Gateway",
        description="Multi-provider LLM API Gateway supporting Anthropic, OpenAI, Google Gemini, and local LLMs",
        version="2.0.0",
    )

    # Load schema registry for validation
    try:
        registry = load_registry("/app/schemas")
    except Exception:
        registry = None
        log.warning("Schema registry not available, validation disabled")

    # Build providers
    providers = build_providers(settings)

    # Create LLM client for new endpoints
    llm_client: Optional[LLMClient] = None
    try:
        llm_client = LLMClient()
    except Exception as e:
        log.warning(f"Failed to create LLM client: {e}")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        """Health check endpoint."""
        available_providers = [
            name for name in ["anthropic", "openai", "google", "local"]
            if name in providers
        ]
        return {
            "status": "ok",
            "providers": available_providers,
            "test_mode": settings.test_mode,
        }

    @app.get("/v1/providers")
    def list_providers() -> Dict[str, Any]:
        """List available providers and their status."""
        provider_status = {}
        for name in ["anthropic", "openai", "google", "local"]:
            provider_status[name] = {
                "available": settings.is_provider_available(name),
                "enabled": name in providers,
            }
        return {"providers": provider_status}

    def _validate_result(result_json: Dict[str, Any], schema_name: str) -> bool:
        """Validate result against schema."""
        if not registry:
            return True  # Skip validation if no registry

        schema = registry.objects.get(schema_name)
        if not schema:
            raise HTTPException(status_code=400, detail=f"unknown schema {schema_name}")
        res = validate_payload(registry, schema.get("x_event_type", schema_name), result_json)
        if not res.ok:
            return False
        return True

    def _validate_object(result_json: Dict[str, Any], schema_name: str) -> bool:
        """Validate object against JSON schema."""
        if not registry:
            return True  # Skip validation if no registry

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
        """Extract structured data from text (legacy endpoint).

        This endpoint provides backwards compatibility with the
        original extraction API.
        """
        provider_order: List[str] = req.provider_preference or list(settings.provider_order)
        provider_order = [p for p in provider_order if p]
        used_provider: str | None = None
        warnings: List[str] = []
        last_error: Dict[str, Any] | None = None
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
                except ProviderError as exc:
                    last_error = {"type": "provider_error", "message": str(exc)}
                    warnings.append(str(exc))
                    time.sleep(min(settings.timeout_s, 0.1 * (attempt + 1)))
                    continue
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

    @app.post("/v1/predict", response_model=PredictResponse)
    def predict(req: PredictRequest) -> PredictResponse:
        """General prediction endpoint.

        Make a prediction using configured LLM providers with
        automatic fallback support.
        """
        if not llm_client:
            raise HTTPException(status_code=503, detail="LLM client not available")

        try:
            result, usage = llm_client.predict(
                prompt=req.prompt,
                agent_name=req.agent_name,
                task_type=req.task_type,
                provider=req.provider,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                system_prompt=req.system_prompt,
            )

            return PredictResponse(
                ok=True,
                provider_used=usage.get("provider"),
                model_used=usage.get("model"),
                result=result,
                usage=usage,
            )
        except Exception as e:
            log.error(f"Prediction failed: {e}")
            return PredictResponse(
                ok=False,
                error={"type": "error", "message": str(e)},
            )

    @app.post("/v1/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        """Chat completion endpoint.

        Send a conversation to the LLM and get a response.
        """
        if not llm_client:
            raise HTTPException(status_code=503, detail="LLM client not available")

        try:
            messages = [{"role": m.role, "content": m.content} for m in req.messages]

            result, usage = llm_client.chat(
                messages=messages,
                agent_name=req.agent_name,
                task_type=req.task_type,
                provider=req.provider,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                system_prompt=req.system_prompt,
                tools=req.tools,
            )

            return ChatResponse(
                ok=True,
                provider_used=usage.get("provider"),
                model_used=usage.get("model"),
                result=result,
                usage=usage,
            )
        except Exception as e:
            log.error(f"Chat failed: {e}")
            return ChatResponse(
                ok=False,
                error={"type": "error", "message": str(e)},
            )

    @app.get("/v1/usage")
    def get_usage() -> Dict[str, Any]:
        """Get usage statistics."""
        if not llm_client:
            return {"error": "LLM client not available"}

        return {
            "usage": llm_client.get_usage_stats(),
            "estimated_cost": llm_client.estimate_cost(),
        }

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
