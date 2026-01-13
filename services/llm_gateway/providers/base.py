from __future__ import annotations

import hashlib
from typing import Any, Dict, Tuple


class ProviderError(Exception):
    pass


class Provider:
    def __init__(self, name: str):
        self.name = name

    def predict(self, prompt: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        raise NotImplementedError

    @staticmethod
    def safe_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
