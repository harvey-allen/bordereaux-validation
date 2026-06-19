from __future__ import annotations

import difflib
from typing import Any

from app.common.utilities.field_configuration import (
    load_pack_field_configuration,
    normalize_field_name,
)


class FieldMappingService:
    async def estimate_field_mapping(
        self,
        *,
        test_pack: str,
        territory: str,
        headers: list[str],
        mandatory_fields: list[str],
    ) -> dict[str, Any]:
        config = load_pack_field_configuration(test_pack)
        if not config:
            return {
                "estimated_mappings": {},
                "matched_count": 0,
                "unmatched_headers": headers,
                "unmatched_fields": mandatory_fields,
                "confidence_summary": {},
            }

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

        all_schema_fields: list[str] = []
        mandatory_rows = territory_entry.get("mandatory", []) if isinstance(territory_entry, dict) else []
        for row in mandatory_rows:
            if isinstance(row, dict):
                field_name = str(row.get("field") or "").strip()
                if field_name:
                    all_schema_fields.append(field_name)

        conditional_rows = territory_entry.get("conditional", []) if isinstance(territory_entry, dict) else []
        for row in conditional_rows:
            if isinstance(row, dict):
                field_name = str(row.get("field") or "").strip()
                if field_name:
                    all_schema_fields.append(field_name)

        normalized_fields = {normalize_field_name(f): f for f in all_schema_fields if f}

        estimated_mappings: dict[str, str] = {}
        matched_headers: set[str] = set()
        confidence_summary: dict[str, str] = {}

        mandatory_threshold = 0.5
        conditional_threshold = 0.7

        for header in headers:
            if not header or not header.strip():
                continue

            norm_header = normalize_field_name(header)
            if not norm_header:
                continue

            best_match = None
            best_ratio = 0.0
            is_mandatory_match = False

            for norm_field, orig_field in normalized_fields.items():
                ratio = difflib.SequenceMatcher(None, norm_header, norm_field).ratio()
                is_mandatory = orig_field in mandatory_fields
                threshold = mandatory_threshold if is_mandatory else conditional_threshold
                if ratio > best_ratio and ratio >= threshold:
                    best_ratio = ratio
                    best_match = orig_field
                    is_mandatory_match = is_mandatory

            if best_match:
                estimated_mappings[header] = best_match
                matched_headers.add(header)

                if best_ratio >= 0.9:
                    confidence_summary[header] = "high"
                elif best_ratio >= mandatory_threshold and (is_mandatory_match or best_ratio >= conditional_threshold):
                    confidence_summary[header] = "medium" if not is_mandatory_match else "low"
                else:
                    confidence_summary[header] = "low"

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


field_mapping_service = FieldMappingService()
