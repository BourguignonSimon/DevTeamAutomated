from __future__ import annotations

import os
from dataclasses import dataclass

from core.config import Settings


@dataclass(frozen=True)
class OrderIntakeSettings(Settings):
    storage_dir: str = os.getenv("STORAGE_DIR", "/storage")
    artifact_ttl_s: int = int(os.getenv("ARTIFACT_TTL_S", "604800"))
    validation_set_key: str = os.getenv("VALIDATION_SET_KEY", "audit:orders:pending_validation")
    export_lock_ttl_ms: int = int(os.getenv("EXPORT_LOCK_TTL_MS", "120000"))
    service_name: str = os.getenv("SERVICE_NAME", "order_intake_agent")
