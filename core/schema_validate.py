from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from core.schema_registry import SchemaRegistry


@dataclass
class ValidationResult:
    ok: bool
    error: Optional[str] = None
    schema_id: Optional[str] = None


def _validate(schema: dict, instance: Any, *, store: dict | None = None) -> ValidationResult:
    resolver = RefResolver.from_schema(schema, store=store) if store else None
    v = Draft202012Validator(schema, format_checker=FormatChecker(), resolver=resolver)
    errors = sorted(v.iter_errors(instance), key=lambda e: e.path)
    if errors:
        e = errors[0]
        return ValidationResult(False, f"{e.message}", schema.get("$id"))
    return ValidationResult(True, None, schema.get("$id"))


def validate_envelope(reg: SchemaRegistry, envelope: dict) -> ValidationResult:
    return _validate(reg.envelope, envelope, store=reg.objects_by_id)


def validate_payload(reg: SchemaRegistry, event_type: str, payload: Any) -> ValidationResult:
    schema = reg.payloads.get(event_type)
    if not schema:
        return ValidationResult(False, f"no schema for event_type={event_type}", None)
    return _validate(schema, payload, store=reg.objects_by_id)
