from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExtractionInput(BaseModel):
    extracted_text: Optional[str] = None
    extracted_table: Optional[List[Dict[str, Any]]] = None
    hints: Dict[str, Any] = Field(default_factory=dict)


class ExtractionRequest(BaseModel):
    request_id: str
    correlation_id: str
    provider_preference: List[str] = Field(default_factory=list)
    input: ExtractionInput
    output_schema_name: str
    strict: bool = True


class ExtractionResponse(BaseModel):
    ok: bool
    provider_used: Optional[str] = None
    result_json: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[Dict[str, Any]] = None
