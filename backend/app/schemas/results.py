"""Pydantic schemas for the Results domain (history, statistics, saved versions, KPIs)."""
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ValidationHistoryItem(BaseModel):
    """A validation run in the history."""
    id: int
    timestamp: str
    test_packs: str
    workbook_name: Optional[str]
    sheet_name: Optional[str]
    range_address: Optional[str]
    total_rows: int
    total_cells: int
    failed_cells: int
    passed_cells: int
    status: str
    pass_rate: float
    tagged_cells: list[dict[str, Any]] = Field(default_factory=list)
    tests: list[dict[str, Any]]


class ValidationHistoryResponse(BaseModel):
    """Response with validation history."""
    runs: list[ValidationHistoryItem]
    total: int


class TestStatisticsResponse(BaseModel):
    """Response with aggregated test statistics."""
    period_days: int
    total_runs: int
    total_cells: int
    total_passed: int
    total_failed: int
    pass_rate: float
    tests: dict[str, dict[str, Any]]


class FailedTestItem(BaseModel):
    umr: Optional[str] = None  # Legacy
    id: Optional[str] = None   # New name
    test_id: str

    @property
    def umr_or_id(self) -> str:
        """Return id if present, else umr, else empty string."""
        return (self.id or self.umr or "").strip()


class SaveResultsVersionRequest(BaseModel):
    workbook_name: Optional[str] = None
    sheet_name: str
    test_pack: Optional[str] = None
    test_packs: Union[str, Optional[list[str]]] = None  # legacy fallback
    failed_tests: list[FailedTestItem] = Field(default_factory=list)
    passed_tests: list[str] = Field(default_factory=list)
    passed_umrs: list[str] = Field(default_factory=list)
    mapped_headers: dict[str, str] = Field(default_factory=dict)
    saved_data: list[dict[str, Any]] = Field(default_factory=list)
    tagged_cells: list[dict[str, Any]] = Field(default_factory=list)
    version_name: Optional[str] = Field(default=None, max_length=32)
    kpis: dict[str, Any] = Field(default_factory=dict)
    summary_metrics: dict[str, Any] = Field(default_factory=dict)


class SavedResultsVersionItem(BaseModel):
    id: int
    created_at: str
    updated_at: str
    version_name: Optional[str] = None
    workbook_name: Optional[str] = None
    sheet_name: Optional[str] = None
    current_scope: bool = False


class SavedResultsVersionListResponse(BaseModel):
    versions: list[SavedResultsVersionItem]


class SavedResultsVersionPayloadResponse(BaseModel):
    id: int
    sheet_key_id: int
    created_at: str
    updated_at: str
    test_pack: str
    version_name: Optional[str] = None
    workbook_name: str
    sheet_name: str
    mapped_headers: dict[str, str] = Field(default_factory=dict)
    saved_data: list[dict[str, Any]] = Field(default_factory=list)
    tagged_cells: list[dict[str, Any]] = Field(default_factory=list)
    pack_config: dict[str, Any] = Field(default_factory=dict)


class LatestResultsVersionResponse(BaseModel):
    id: int
    created_at: str
    updated_at: str
    workbook_name: str
    sheet_name: str
    version_name: Optional[str] = None
    results: dict[str, Any]


class VersionKpiSummary(BaseModel):
    submissions_failed: int
    submissions_failed_pct: Optional[float] = None
    fields_failed: Optional[int] = None
    fields_failed_pct: Optional[float] = None
    tests_failed: int
    tests_failed_pct: Optional[float] = None
    tests_passed_pct: Optional[float] = None


class PreviousVersionSummary(BaseModel):
    id: int
    workbook_name: str
    sheet_name: str
    created_at: str
    updated_at: str
    version_name: Optional[str] = None
    kpis: VersionKpiSummary


class VersionTrendPoint(BaseModel):
    id: int
    workbook_name: str
    sheet_name: str
    created_at: str
    updated_at: str
    version_name: Optional[str] = None
    test_passed_pct: Optional[float] = None
    submissions_failed_pct: Optional[float] = None
    fields_failed_pct: Optional[float] = None


class VersionComparisonResponse(BaseModel):
    previous_version: Optional[PreviousVersionSummary] = None
    trend: list[VersionTrendPoint] = Field(default_factory=list)
