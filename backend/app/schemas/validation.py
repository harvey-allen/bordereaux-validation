"""Pydantic schemas for the Validation domain."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ValidateRequest(BaseModel):
    addresses: list[list[str]] = Field(description="A 2D array of A1 addresses for each cell in range")
    values: list[list[Any]] = Field(description="A 2D array of values matching addresses")
    columnRules: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="Validation rules keyed by zero-based column index as string",
    )
    testPacks: list[str] = Field(default_factory=list, description="A list of pack names to execute")
    hasHeaderRow: bool = Field(default=True, description="Treat first selected row as header for pack-based tests")
    packConfigs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional per-pack config, e.g. UMR",
    )
    includeCoverage: bool = Field(default=True, description="Include per-pack coverage report in response")
    storeResults: bool = Field(default=True, description="Store per-run test summaries in test_results")
    workbookName: Optional[str] = Field(default=None, description="Name of the workbook being validated")
    sheetName: Optional[str] = Field(default=None, description="Name of the sheet being validated")
    rangeAddress: Optional[str] = Field(default=None, description="Address of the range being validated")


class ValidateResponse(BaseModel):
    results: list[dict[str, Any]]
    coverage: Optional[dict[str, Any]] = None
    usage: Optional[dict[str, Any]] = None
    validation_run_id: Optional[int] = None
