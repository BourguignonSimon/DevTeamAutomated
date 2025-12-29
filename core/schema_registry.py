from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Any


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class SchemaRegistry:
    envelope: Dict[str, Any]
    objects: Dict[str, Dict[str, Any]]
    payloads: Dict[str, Dict[str, Any]]  # event_type -> schema


def load_registry(base_dir: str) -> SchemaRegistry:
    envelope = _load_json(os.path.join(base_dir, "envelope", "event_envelope.v1.schema.json"))

    objects: Dict[str, Dict[str, Any]] = {}
    obj_dir = os.path.join(base_dir, "objects")
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
