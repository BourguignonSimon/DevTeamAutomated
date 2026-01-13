from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException

from core.schema_registry import load_registry
from core.schema_validate import validate_payload
from services.llm_gateway.models import ExtractionRequest, ExtractionResponse
from services.llm_gateway.providers.anthropic import AnthropicProvider
from services.llm_gateway.providers.base import Provider, ProviderError
from services.llm_gateway.providers.fake import FakeProvider
from services.llm_gateway.providers.gemini import GeminiProvider
from services.llm_gateway.providers.openai import OpenAIProvider
from services.llm_gateway.settings import GatewaySettings

log = logging.getLogger(__name__)


def build_providers(settings: GatewaySettings) -> Dict[str, Provider]:
    providers: Dict[str, Provider] = {
        "anthropic": AnthropicProvider(settings.anthropic_api_key),
        "openai": OpenAIProvider(settings.openai_api_key),
        "gemini": GeminiProvider(settings.gemini_api_key),
    }
    providers["fake"] = FakeProvider()
    return providers


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    settings = settings or GatewaySettings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    app = FastAPI()
    registry = load_registry("/app/schemas")
    providers = build_providers(settings)

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    def _validate_result(result_json: Dict[str, Any], schema_name: str) -> bool:
        schema = registry.objects.get(schema_name)
        if not schema:
            raise HTTPException(status_code=400, detail=f"unknown schema {schema_name}")
        res = validate_payload(registry, schema.get("x_event_type", schema_name), result_json)
        if not res.ok:
            return False
        return True

    def _validate_object(result_json: Dict[str, Any], schema_name: str) -> bool:
        schema = registry.objects.get(schema_name)
        if not schema:
            return False
        from jsonschema import Draft202012Validator, RefResolver
        validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=registry.objects_by_id))
        errors = list(validator.iter_errors(result_json))
        return not errors

    @app.post("/v1/extract/order", response_model=ExtractionResponse)
    def extract(req: ExtractionRequest) -> ExtractionResponse:
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
                except ProviderError as exc:  # pragma: no cover - depends on provider behavior
                    last_error = {"type": "provider_error", "message": str(exc)}
                    warnings.append(str(exc))
                    time.sleep(min(settings.timeout_s, 0.1 * (attempt + 1)))
                    continue
                except Exception as exc:  # pragma: no cover
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


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
