"""Canonical normalization helpers.

Phase 2 compatibility shim to keep behaviour identical while introducing the
new `app.common.utilities` namespace.
"""
from app.utils.normalization import (  # noqa: F401
    UNKNOWN_PACK,
    UNKNOWN_SHEET,
    UNKNOWN_WORKBOOK,
    normalize_pack_storage_value,
    normalize_scope_value,
)

__all__ = [
    "UNKNOWN_PACK",
    "UNKNOWN_SHEET",
    "UNKNOWN_WORKBOOK",
    "normalize_pack_storage_value",
    "normalize_scope_value",
]
