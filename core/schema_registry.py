from __future__ import annotations

import json
import os
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_base_dir(base_dir: str) -> str:
    """Return the first existing schema directory.

    Tests pass "/app/schemas" as the base directory, but when running locally
    the repository is checked out elsewhere. This helper falls back to the
    project's bundled ``schemas`` folder whenever the requested path does not
    exist.
    """

    candidates = [base_dir]

    env_base = os.getenv("SCHEMA_BASE_DIR")
    if env_base:
        candidates.append(env_base)

    repo_schemas = Path(__file__).resolve().parent.parent / "schemas"
    candidates.append(str(repo_schemas))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(f"Unable to locate schema directory from {base_dir}")


@dataclass
class SchemaRegistry:
    envelope: Dict[str, Any]
    objects: Dict[str, Dict[str, Any]]
    payloads: Dict[str, Dict[str, Any]]  # event_type -> schema


def load_registry(base_dir: str) -> SchemaRegistry:
    base_dir = _resolve_base_dir(base_dir)
    envelope = _load_json(os.path.join(base_dir, "envelope", "event_envelope.v1.schema.json"))

    objects: Dict[str, Dict[str, Any]] = {}
    obj_dir = os.path.join(base_dir, "objects")
    if os.path.exists(obj_dir):
        for name in os.listdir(obj_dir):
            if name.endswith(".json"):
                objects[name] = _load_json(os.path.join(obj_dir, name))

    payloads: Dict[str, Dict[str, Any]] = {}
    ev_dir = os.path.join(base_dir, "events")
    for name in os.listdir(ev_dir):
        if not name.endswith(".json"):
            continue
        sch = _load_json(os.path.join(ev_dir, name))
        event_type = sch.get("x_event_type")
        if not event_type:
            raise ValueError(f"schema {name} missing x_event_type")
        if event_type in payloads:
            raise ValueError(f"duplicate schema for event_type={event_type}")
        payloads[event_type] = sch

    return SchemaRegistry(envelope=envelope, objects=objects, payloads=payloads)
