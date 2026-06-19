"""Pydantic schemas for the Subscription / Auth domain."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UsageResponse(BaseModel):
    tier: str
    requests_today: int
    requests_this_minute: int
    daily_limit: int
    minute_limit: int
    daily_remaining: int
    minute_remaining: int


class SubscriptionInfoResponse(BaseModel):
    tier: str
    owner_email: str
    display_name: Optional[str]
    is_active: bool
    expires_at: Optional[str]
    allowed_packs: Optional[list[str]]
    max_cells_per_request: int


class RegisterRequest(BaseModel):
    """Request to register/login an Excel user."""
    excel_user_id: str = Field(description="Unique Excel user ID from Office.js")
    email: str = Field(description="User's email address")
    display_name: Optional[str] = Field(default=None, description="User's display name")
    organisation_name: Optional[str] = Field(default=None, description="Optional organisation name")


class RegisterResponse(BaseModel):
    """Response with API key for new registrations."""
    api_key: Optional[str] = Field(description="API key (only returned for new registrations)")
    tier: str
    is_new_user: bool
    message: str


class TestPackCatalogResponse(BaseModel):
    all_packs: list[str]
    allowed_packs: Optional[list[str]]
    default_pack: Optional[str]
