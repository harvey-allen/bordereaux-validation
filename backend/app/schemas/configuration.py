"""Pydantic schemas for the Configuration domain (pack config, territories, templates, field mapping)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PackConfigRequest(BaseModel):
    test_pack: str
    sheet_name: str
    pack_config: dict[str, Any] = Field(default_factory=dict)
    workbook_name: Optional[str] = None


class PackConfigResponse(BaseModel):
    test_pack: str
    sheet_name: str
    workbook_name: Optional[str] = None
    pack_config: dict[str, Any] = Field(default_factory=dict)


class TerritoryOptionsResponse(BaseModel):
    test_pack: str
    territories: list[str]


class TemplateResponse(BaseModel):
    """Response containing template field headers for a test pack."""
    test_pack: str
    territory: str
    headers: list[str]
    total_fields: int


class FieldMappingEstimationRequest(BaseModel):
    """Request to estimate field mapping from headers to schema."""
    test_pack: str
    territory: str
    headers: list[str] = Field(description="Column headers from the uploaded data")


class FieldMappingEstimationResponse(BaseModel):
    """Response containing estimated field mapping."""
    test_pack: str
    territory: str
    estimated_mappings: dict[str, str] = Field(
        description="Estimated mappings from headers to schema fields"
    )
    matched_count: int = Field(description="Number of successfully matched headers")
    unmatched_headers: list[str] = Field(description="Headers that could not be matched")
    unmatched_fields: list[str] = Field(description="Schema fields that were not matched")
    confidence_summary: dict[str, str] = Field(
        description="Mapping of matched headers to confidence level (high/medium/low)"
    )
