import hashlib
import json
from pathlib import Path


def test_prompt_hash_matches_manifest():
    root = Path(__file__).resolve().parents[1] / "prompts"
    manifest = json.loads((root / "versions.json").read_text())
    for name, meta in manifest.items():
        content = (root / name).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        assert meta["hash"] == digest
        assert meta["version"].count(".") == 2
