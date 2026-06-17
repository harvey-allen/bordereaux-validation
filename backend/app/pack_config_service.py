"""Service for persisted test-pack configuration per user/sheet."""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SheetKey, PackConfiguration
from app.utils.normalization import (
    UNKNOWN_SHEET,
    UNKNOWN_WORKBOOK,
    normalize_pack_storage_value,
    normalize_scope_value,
)
from app.validation import _normalize_field_name


class PackConfigService:
    """CRUD for pack configurations."""

    async def _find_sheet_key(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        workbook_name: str | None,
        sheet_name: str | None,
        test_pack: str | None = None,
    ) -> SheetKey | None:
        normalized_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
        normalized_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)
        normalized_pack = normalize_pack_storage_value(test_pack)

        result = await db.execute(
            select(SheetKey)
            .where(SheetKey.organisation_id == organisation_id)
            .where(SheetKey.workbook_name == normalized_workbook)
            .where(SheetKey.sheet_name == normalized_sheet)
            .where(SheetKey.test_pack == normalized_pack)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_sheet_key(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        workbook_name: str | None,
        sheet_name: str | None,
        test_pack: str | None = None,
    ) -> SheetKey:
        normalized_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
        normalized_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)
        normalized_pack = normalize_pack_storage_value(test_pack)

        result = await db.execute(
            select(SheetKey)
            .where(SheetKey.organisation_id == organisation_id)
            .where(SheetKey.workbook_name == normalized_workbook)
            .where(SheetKey.sheet_name == normalized_sheet)
            .where(SheetKey.test_pack == normalized_pack)
        )
        sheet_key = result.scalar_one_or_none()
        
        now = datetime.now(timezone.utc)
        
        if sheet_key is not None:
            return sheet_key

        sheet_key = SheetKey(
            organisation_id=organisation_id,
            workbook_name=normalized_workbook,
            sheet_name=normalized_sheet,
            test_pack=normalized_pack,
            created_at=now,
            updated_at=now,
        )
        db.add(sheet_key)
        await db.flush()
        return sheet_key

    async def get_config(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
    ) -> dict[str, Any] | None:
        sheet_key = await self._find_sheet_key(
            db,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )
        if sheet_key is None:
            return None

        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key.id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        return dict(item.config_json or {})

    async def upsert_config(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
        pack_config: dict[str, Any],
    ) -> dict[str, Any]:
        sheet_key = await self._get_or_create_sheet_key(
            db,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )

        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key.id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        normalized_config = dict(pack_config or {})

        if item is None:
            item = PackConfiguration(
                user_id=user_id,
                sheet_key_id=int(sheet_key.id),
                sheet_name=sheet_name,
                test_pack=test_pack,
                workbook_name=workbook_name,
                config_json=normalized_config,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
        else:
            item.sheet_key_id = int(sheet_key.id)
            item.workbook_name = workbook_name or item.workbook_name
            item.config_json = normalized_config
            item.updated_at = now

        await db.commit()
        return normalized_config


pack_config_service = PackConfigService()


async def estimate_field_mapping(
    test_pack: str,
    territory: str,
    headers: list[str],
    mandatory_fields: list[str],
) -> dict[str, Any]:
    """
    Estimate field mapping from uploaded headers to schema fields using fuzzy matching.
    
    Uses two-tier confidence thresholds:
    - Mandatory fields: low confidence threshold (unsafe matches allowed)
    - Conditional fields: medium confidence threshold (stricter)
    
    Args:
        test_pack: The test pack name
        territory: The territory
        headers: List of column headers from uploaded data
        mandatory_fields: List of mandatory schema fields for this pack/territory
    
    Returns:
        Dictionary with estimated_mappings, matched_count, unmatched lists, and confidence_summary
    """
    from app.validation import _load_pack_field_configuration
    
    # Load full field configuration to get all possible schema fields
    config = _load_pack_field_configuration(test_pack)
    if not config:
        return {
            "estimated_mappings": {},
            "matched_count": 0,
            "unmatched_headers": headers,
            "unmatched_fields": mandatory_fields,
            "confidence_summary": {},
        }
    
    # Get territory-specific fields (both mandatory and conditional)
    territory_lookup = {str(name).strip().lower(): str(name) for name in config.keys()}
    selected_key = territory_lookup.get(str(territory).strip().lower())
    if not selected_key:
        return {
            "estimated_mappings": {},
            "matched_count": 0,
            "unmatched_headers": headers,
            "unmatched_fields": mandatory_fields,
            "confidence_summary": {},
        }
    
    territory_entry = config.get(selected_key, {})
    if not isinstance(territory_entry, dict):
        return {
            "estimated_mappings": {},
            "matched_count": 0,
            "unmatched_headers": headers,
            "unmatched_fields": mandatory_fields,
            "confidence_summary": {},
        }
    
    # Collect all schema fields (mandatory and conditional)
    all_schema_fields: list[str] = []
    conditional_fields: set[str] = set()
    
    # Mandatory fields
    mandatory_rows = territory_entry.get("mandatory", []) if isinstance(territory_entry, dict) else []
    for row in mandatory_rows:
        if isinstance(row, dict):
            field_name = str(row.get("field") or "").strip()
            if field_name:
                all_schema_fields.append(field_name)
    
    # Conditional fields
    conditional_rows = territory_entry.get("conditional", []) if isinstance(territory_entry, dict) else []
    for row in conditional_rows:
        if isinstance(row, dict):
            field_name = str(row.get("field") or "").strip()
            if field_name:
                all_schema_fields.append(field_name)
                conditional_fields.add(field_name)
    
    # Normalize schema fields for matching
    normalized_fields = {_normalize_field_name(f): f for f in all_schema_fields if f}
    
    estimated_mappings: dict[str, str] = {}
    matched_headers: set[str] = set()
    confidence_summary: dict[str, str] = {}
    
    # Thresholds based on field type
    # Mandatory fields allow low confidence (unsafe) matches: >= 0.5
    # Conditional fields require medium confidence: >= 0.7
    mandatory_threshold = 0.5
    conditional_threshold = 0.7
    
    # Match each header to schema fields using fuzzy matching
    for header in headers:
        if not header or not header.strip():
            continue
        
        norm_header = _normalize_field_name(header)
        if not norm_header:
            continue
        
        best_match = None
        best_ratio = 0.0
        is_mandatory_match = False
        
        # Try to find best match among all schema fields
        for norm_field, orig_field in normalized_fields.items():
            # Use SequenceMatcher for token-based similarity
            ratio = difflib.SequenceMatcher(None, norm_header, norm_field).ratio()
            
            # Determine if this field is mandatory or conditional
            is_mandatory = orig_field in mandatory_fields
            threshold = mandatory_threshold if is_mandatory else conditional_threshold
            
            # Update best match if this one is better
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = orig_field
                is_mandatory_match = is_mandatory
        
        if best_match:
            estimated_mappings[header] = best_match
            matched_headers.add(header)
            
            # Categorize confidence level
            if best_ratio >= 0.9:
                confidence_summary[header] = "high"
            elif best_ratio >= mandatory_threshold and (is_mandatory_match or best_ratio >= conditional_threshold):
                confidence_summary[header] = "medium" if not is_mandatory_match else "low"
            else:
                confidence_summary[header] = "low"
    
    # Unmatched items
    unmatched_headers = [h for h in headers if h and h not in matched_headers]
    matched_field_names = set(estimated_mappings.values())
    unmatched_fields = [f for f in all_schema_fields if f not in matched_field_names]
    
    return {
        "estimated_mappings": estimated_mappings,
        "matched_count": len(estimated_mappings),
        "unmatched_headers": unmatched_headers,
        "unmatched_fields": unmatched_fields,
        "confidence_summary": confidence_summary,
    }

