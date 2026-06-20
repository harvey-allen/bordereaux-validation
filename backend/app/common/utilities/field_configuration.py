from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from app.testpacks.core import get_pack_name_variants, normalize_pack_name

FIELD_CONFIG_DIR = Path(__file__).parents[2] / "testpacks" / "field_configurations"


def normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


@lru_cache(maxsize=16)
def load_pack_field_configuration(pack_name: str) -> dict[str, Any]:
    normalized_pack = normalize_pack_name(pack_name)
    for candidate_pack in get_pack_name_variants(normalized_pack):
        config_path = FIELD_CONFIG_DIR / f"{candidate_pack}.json"
        if not config_path.exists():
            continue
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            return raw
    return {}
