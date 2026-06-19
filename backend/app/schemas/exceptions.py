"""Pydantic schemas for the Exception Management domain."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExceptionItem(BaseModel):
    """Single exception response item."""
    id: int
    exception_id: str
    linked_field: Optional[str] = None
    linked_umr: Optional[str] = None
    # Legacy alias for linked_field in older clients.
    test_id: Optional[str] = None
    description: str
    status: str
    author_id: Optional[int] = None
    created_at: str
    updated_at: str


class ExceptionCreateRequest(BaseModel):
    """Request to create a new exception."""
    exception_id: str = Field(description="Unique exception ID within organisation")
    linked_field: Optional[str] = Field(default=None, description="Optional linked field from selected test pack")
    linked_umr: Optional[str] = Field(default=None, description="Optional linked UMR value")
    test_id: Optional[str] = Field(default=None, description="Deprecated alias for linked_field")
    description: str = Field(description="Exception description")
    status: str = Field(default="to do", description="Exception status")


class ExceptionUpdateRequest(BaseModel):
    """Request to update an exception."""
    exception_id: Optional[str] = Field(default=None, description="Exception ID")
    linked_field: Optional[str] = Field(default=None, description="Linked field")
    linked_umr: Optional[str] = Field(default=None, description="Linked UMR")
    test_id: Optional[str] = Field(default=None, description="Deprecated alias for linked_field")
    description: Optional[str] = Field(default=None, description="Exception description")
    status: Optional[str] = Field(default=None, description="Exception status")


class ExceptionListResponse(BaseModel):
    """List of exceptions."""
    exceptions: list[ExceptionItem]


class ExceptionApplyRequest(BaseModel):
    """Request to apply exception to cells."""
    exception_id: str = Field(description="Exception ID to apply")
    addresses: list[str] = Field(description="List of cell addresses to apply exception to")
    tagged_cells: list[dict[str, Any]] = Field(default_factory=list, description="Optional full tagged-cell records")
    sheet_name: str = Field(description="Sheet name containing the tagged cells")
    workbook_name: Optional[str] = Field(default=None, description="Workbook name for the tagged cells")
    test_pack: Optional[str] = Field(default=None, description="Optional test pack scope")


class ExceptionAnalyticsItem(BaseModel):
    """Exception with tag count for analytics visualization."""
    exception_id: str
    description: str
    tag_count: int
    status: str


class ExceptionAnalyticsResponse(BaseModel):
    """Response for exception analytics endpoint."""
    analytics: list[ExceptionAnalyticsItem]
