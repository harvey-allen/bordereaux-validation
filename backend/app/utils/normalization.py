"""Shared normalization helpers for persistence and lookups."""

from __future__ import annotations

from app.testpacks.core import normalize_pack_name


UNKNOWN_WORKBOOK = "__unknown_workbook__"
UNKNOWN_SHEET = "__unknown_sheet__"
UNKNOWN_PACK = "__unknown_pack__"


def normalize_scope_value(value: str | None, *, fallback: str) -> str:
    """Normalize scope values like workbook/sheet names for consistent keys."""
    normalized = str(value or "").strip().lower()
    return normalized or fallback


def normalize_pack_storage_value(value: str | None) -> str:
    """Normalize persisted pack key values, with a safe unknown fallback."""
    normalized = normalize_scope_value(value, fallback=UNKNOWN_PACK)
    if normalized == UNKNOWN_PACK:
        return UNKNOWN_PACK
    canonical = normalize_pack_name(normalized)
    return canonical or UNKNOWN_PACK
