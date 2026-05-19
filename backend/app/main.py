from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

from app.auth import (
    Subscription,
    SubscriptionTier,
    check_cell_limit,
    check_pack_access,
    check_rate_limit,
    get_current_subscription,
    subscription_store,
)
from app.validation import validate_grid_with_packs_report

# Database imports (optional - gracefully handle if DB not available)
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db, init_db, close_db, async_session_maker
    from app.subscription_service import subscription_service
    from app.results_service import store_validation_results, get_validation_history, get_validation_run, get_test_statistics
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


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
        description="Optional per-pack config, e.g. RefColumn",
    )
    includeCoverage: bool = Field(default=True, description="Include per-pack coverage report in response")
    storeResults: bool = Field(default=True, description="Store results in database for history")
    workbookName: str | None = Field(default=None, description="Name of the workbook being validated")
    sheetName: str | None = Field(default=None, description="Name of the sheet being validated")
    rangeAddress: str | None = Field(default=None, description="Address of the range being validated")


class ValidateResponse(BaseModel):
    results: list[dict[str, Any]]
    coverage: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    validation_run_id: int | None = None


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
    is_active: bool
    expires_at: str | None
    allowed_packs: list[str] | None
    max_cells_per_request: int


class RegisterRequest(BaseModel):
    """Request to register/login an Excel user."""
    excel_user_id: str = Field(description="Unique Excel user ID from Office.js")
    email: str = Field(description="User's email address")
    display_name: str | None = Field(default=None, description="User's display name")


class RegisterResponse(BaseModel):
    """Response with API key for new registrations."""
    api_key: str | None = Field(description="API key (only returned for new registrations)")
    tier: str
    is_new_user: bool
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize and cleanup database."""
    if DB_AVAILABLE:
        try:
            await init_db()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Database initialization failed: {e}")
            print("Running in fallback mode with in-memory storage")
    yield
    if DB_AVAILABLE:
        try:
            await close_db()
        except Exception:
            pass


app = FastAPI(
    title="Bordereaux Validation API",
    version="1.0.0",
    description="Excel data validation API for bordereaux processing with subscription-based access.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "db_available": str(DB_AVAILABLE)}


@app.post("/api/v1/register", response_model=RegisterResponse)
async def register_user(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,
) -> RegisterResponse:
    """
    Register or login an Excel user.
    
    If the user already exists, returns their subscription info.
    If new, creates a subscription with the default tier and returns an API key.
    
    The API key is ONLY returned once during initial registration.
    Users should store it securely.
    """
    if not DB_AVAILABLE or db is None:
        # Fallback to in-memory store
        raise HTTPException(
            status_code=503,
            detail="Database not available. Using development mode with static API key.",
        )

    subscription, api_key = await subscription_service.get_or_create_subscription(
        db=db,
        excel_user_id=request.excel_user_id,
        email=request.email,
        display_name=request.display_name,
    )

    is_new = bool(api_key)
    
    return RegisterResponse(
        api_key=api_key if is_new else None,
        tier=subscription.tier.value,
        is_new_user=is_new,
        message="Welcome! Save your API key securely - it won't be shown again." if is_new else "Welcome back!",
    )


@app.get("/api/v1/usage", response_model=UsageResponse)
def get_usage(
    subscription: Subscription = Depends(check_rate_limit),
) -> UsageResponse:
    """Get current usage statistics for your API key."""
    stats = subscription_store.get_usage_stats(subscription.api_key_hash)
    return UsageResponse(**stats)


@app.get("/api/v1/subscription", response_model=SubscriptionInfoResponse)
def get_subscription_info(
    subscription: Subscription = Depends(get_current_subscription),
) -> SubscriptionInfoResponse:
    """Get subscription details for your API key."""
    return SubscriptionInfoResponse(
        tier=subscription.tier.value,
        owner_email=subscription.owner_email,
        is_active=subscription.is_active,
        expires_at=subscription.expires_at.isoformat() if subscription.expires_at else None,
        allowed_packs=subscription.config.allowed_packs,
        max_cells_per_request=subscription.config.max_cells_per_request,
    )


@app.post("/validate-range", response_model=ValidateResponse)
async def validate_range(
    payload: ValidateRequest,
    subscription: Subscription = Depends(check_rate_limit),
) -> ValidateResponse:
    """
    Validate a range of Excel cells against test packs.
    
    Requires authentication via X-API-Key header.
    Rate limits apply based on subscription tier.
    """
    if len(payload.addresses) != len(payload.values):
        raise HTTPException(status_code=400, detail="addresses and values must have the same row count")

    if any(len(address_row) != len(value_row) for address_row, value_row in zip(payload.addresses, payload.values)):
        raise HTTPException(status_code=400, detail="each addresses row must match the corresponding values row length")

    # Check subscription limits
    cell_count = sum(len(row) for row in payload.values)
    check_cell_limit(subscription, cell_count)
    
    if payload.testPacks:
        check_pack_access(subscription, payload.testPacks)

    try:
        report = validate_grid_with_packs_report(
            addresses=payload.addresses,
            values=payload.values,
            column_rules=payload.columnRules,
            test_packs=payload.testPacks,
            has_header_row=payload.hasHeaderRow,
            pack_configs=payload.packConfigs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    coverage = report.get("coverage") if payload.includeCoverage else None
    
    # Include usage stats in response
    usage = subscription_store.get_usage_stats(subscription.api_key_hash)
    
    # Store results in database
    validation_run_id = None
    if payload.storeResults and DB_AVAILABLE and coverage:
        try:
            async with async_session_maker() as session:
                # Calculate summary stats from coverage
                summary = coverage.get("summary", {})
                
                validation_run = await store_validation_results(
                    session,
                    api_key=subscription.api_key_hash,  # Already hashed
                    test_packs=payload.testPacks,
                    coverage_data=coverage,
                    workbook_name=payload.workbookName,
                    sheet_name=payload.sheetName,
                    range_address=payload.rangeAddress,
                    total_rows=summary.get("dataRows", 0),
                    total_cells=summary.get("totalCells", 0),
                    failed_cells=summary.get("failedCells", 0),
                    passed_cells=summary.get("passedCells", 0),
                )
                validation_run_id = validation_run.id
        except Exception as e:
            # Don't fail validation if storage fails
            print(f"Failed to store validation results: {e}")
    
    return ValidateResponse(
        results=report["results"], 
        coverage=coverage, 
        usage=usage,
        validation_run_id=validation_run_id,
    )


class ValidationHistoryItem(BaseModel):
    """A validation run in the history."""
    id: int
    timestamp: str
    test_packs: str
    workbook_name: str | None
    sheet_name: str | None
    range_address: str | None
    total_rows: int
    total_cells: int
    failed_cells: int
    passed_cells: int
    status: str
    pass_rate: float
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


@app.get("/api/v1/history", response_model=ValidationHistoryResponse)
async def get_history(
    limit: int = 50,
    offset: int = 0,
    subscription: Subscription = Depends(get_current_subscription),
) -> ValidationHistoryResponse:
    """
    Get validation history for the current user.
    
    Returns a list of past validation runs with their results.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with async_session_maker() as session:
        runs = await get_validation_history(
            session,
            api_key=subscription.api_key_hash,
            limit=limit,
            offset=offset,
        )
        
        items = []
        for run in runs:
            tests = []
            for test in run.test_results:
                tests.append({
                    "test_pack": test.test_pack,
                    "test_name": test.test_name,
                    "description": test.test_description,
                    "severity": test.severity,
                    "evaluated_rows": test.evaluated_rows,
                    "passed_rows": test.passed_rows,
                    "failed_rows": test.failed_rows,
                })
            
            pass_rate = (run.passed_cells / run.total_cells * 100) if run.total_cells > 0 else 100.0
            
            items.append(ValidationHistoryItem(
                id=run.id,
                timestamp=run.timestamp.isoformat(),
                test_packs=run.test_packs,
                workbook_name=run.workbook_name,
                sheet_name=run.sheet_name,
                range_address=run.range_address,
                total_rows=run.total_rows,
                total_cells=run.total_cells,
                failed_cells=run.failed_cells,
                passed_cells=run.passed_cells,
                status=run.status,
                pass_rate=pass_rate,
                tests=tests,
            ))
        
        return ValidationHistoryResponse(runs=items, total=len(items))


@app.get("/api/v1/history/{run_id}")
async def get_history_detail(
    run_id: int,
    subscription: Subscription = Depends(get_current_subscription),
) -> dict[str, Any]:
    """
    Get detailed results for a specific validation run.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with async_session_maker() as session:
        run = await get_validation_run(session, run_id)
        
        if not run:
            raise HTTPException(status_code=404, detail="Validation run not found")
        
        # Check ownership
        if run.api_key_hash != subscription.api_key_hash:
            raise HTTPException(status_code=403, detail="Access denied")
        
        tests = []
        for test in run.test_results:
            tests.append({
                "test_pack": test.test_pack,
                "test_name": test.test_name,
                "description": test.test_description,
                "target_columns": test.target_columns.split(",") if test.target_columns else [],
                "severity": test.severity,
                "severity_weight": test.severity_weight,
                "evaluated_rows": test.evaluated_rows,
                "passed_rows": test.passed_rows,
                "failed_rows": test.failed_rows,
                "failed_refs": test.failed_refs,
            })
        
        return {
            "id": run.id,
            "timestamp": run.timestamp.isoformat(),
            "test_packs": run.test_packs.split(","),
            "workbook_name": run.workbook_name,
            "sheet_name": run.sheet_name,
            "range_address": run.range_address,
            "total_rows": run.total_rows,
            "total_cells": run.total_cells,
            "failed_cells": run.failed_cells,
            "passed_cells": run.passed_cells,
            "status": run.status,
            "error_message": run.error_message,
            "tests": tests,
        }


@app.get("/api/v1/statistics", response_model=TestStatisticsResponse)
async def get_statistics(
    days: int = 30,
    test_pack: str | None = None,
    subscription: Subscription = Depends(get_current_subscription),
) -> TestStatisticsResponse:
    """
    Get aggregated test statistics for analytics.
    
    Shows pass/fail rates over time for each test.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with async_session_maker() as session:
        stats = await get_test_statistics(
            session,
            api_key=subscription.api_key_hash,
            test_pack=test_pack,
            days=days,
        )
        
        return TestStatisticsResponse(**stats)
