from __future__ import annotations

import os
import traceback
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

from app.auth import (
    Subscription,
    SubscriptionTier,
    check_cell_limit,
    check_pack_access,
    subscription_store,
)
from app.testpacks.core import TEST_PACKS, get_pack_name_variants, normalize_pack_name
from app.validation import get_pack_territories, validate_grid_with_packs_report

# Database imports (optional - gracefully handle if DB not available)
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db, init_db, close_db, async_session_maker
    from app.subscription_service import subscription_service
    from app.results_service import store_validation_results, get_validation_history, get_validation_run, get_test_statistics
    from app.pack_config_service import pack_config_service
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
        description="Optional per-pack config, e.g. UMR",
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


class PackConfigRequest(BaseModel):
    test_pack: str
    sheet_name: str
    pack_config: dict[str, Any] = Field(default_factory=dict)
    workbook_name: str | None = None


class PackConfigResponse(BaseModel):
    test_pack: str
    sheet_name: str
    workbook_name: str | None = None
    pack_config: dict[str, Any] = Field(default_factory=dict)


class UsageResponse(BaseModel):
    tier: str
    requests_today: int
    requests_this_minute: int
    daily_limit: int
    minute_limit: int
    daily_remaining: int
    minute_remaining: int


class TerritoryOptionsResponse(BaseModel):
    test_pack: str
    territories: list[str]


class RulesEngineRule(BaseModel):
    pack: str
    rule_id: str
    target_column: str
    description: str
    severity: str
    test_type: str | None = None


class RulesEngineResponse(BaseModel):
    packs: list[str]
    rules: list[RulesEngineRule]


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


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


async def get_authenticated_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,
) -> Subscription:
    """
    Resolve subscription using Excel email first, with API-key fallback for compatibility.

    Priority:
    1) `X-Excel-User-Email` or `X-User-Email` header (DB lookup)
    2) `email` query parameter (DB lookup)
    3) Legacy `X-API-Key` header / `api_key` query parameter
    """
    request_email = _normalize_email(
        request.headers.get("X-Excel-User-Email")
        or request.headers.get("X-User-Email")
        or request.query_params.get("email")
    )

    if DB_AVAILABLE and db is not None and request_email:
        subscription = await subscription_service.get_subscription_by_email(db, request_email)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"No active subscription found for Excel email '{request_email}'.",
            )

        if not subscription.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is inactive.")

        if subscription.is_expired:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription has expired.")

        return subscription

    # Legacy API-key fallback
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key:
        subscription = subscription_store.get_subscription(api_key)

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        if not subscription.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key has been revoked.")

        if subscription.is_expired:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription has expired.")

        return subscription

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing API key or Excel user email. Provide X-Excel-User-Email (preferred) or X-API-Key.",
    )


async def enforce_rate_limit(
    request: Request,
    subscription: Subscription = Depends(get_authenticated_subscription),
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,
) -> Subscription:
    """Rate-limit using DB-backed service when available, else in-memory fallback."""
    if DB_AVAILABLE and db is not None and not subscription.metadata.get("is_dev_key"):
        allowed, error_message = await subscription_service.check_rate_limit(db, subscription)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_message,
                headers={"Retry-After": "60"},
            )

        await subscription_service.record_request(
            db,
            subscription,
            endpoint=request.url.path,
        )
        return subscription

    allowed, error_message = subscription_store.check_rate_limit(subscription)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message,
            headers={"Retry-After": "60"},
        )

    subscription_store.record_request(subscription)
    return subscription


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "db_available": str(DB_AVAILABLE)}


@app.get("/api/v1/field-config/territories", response_model=TerritoryOptionsResponse)
def get_field_config_territories(test_pack: str) -> TerritoryOptionsResponse:
    """Return available territory options for the given test pack."""
    normalized_pack = normalize_pack_name(test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    territories = get_pack_territories(normalized_pack)
    return TerritoryOptionsResponse(test_pack=normalized_pack, territories=territories)


@app.get("/api/v1/rules-engine", response_model=RulesEngineResponse)
def get_rules_engine_rules(test_pack: str | None = None) -> RulesEngineResponse:
    """Return test-pack rules for the Rules Engine UI."""
    requested_pack = normalize_pack_name(test_pack)
    available_packs = sorted(TEST_PACKS.keys())

    if requested_pack:
        if requested_pack not in TEST_PACKS:
            raise HTTPException(status_code=400, detail=f"Unknown test pack '{requested_pack}'")
        packs_to_scan = [requested_pack]
    else:
        packs_to_scan = available_packs

    rules: list[RulesEngineRule] = []
    signature_to_rule_index: dict[tuple[str, str, str, str, str | None], int] = {}

    for pack_name in packs_to_scan:
        pack_cls = TEST_PACKS.get(pack_name)
        if pack_cls is None:
            continue

        for attribute_name in dir(pack_cls):
            if not attribute_name.startswith("test_"):
                continue

            method = getattr(pack_cls, attribute_name)
            if not callable(method) or not getattr(method, "_is_registered_test", False):
                continue

            rule_id = attribute_name.replace("test_", "")
            target_columns = getattr(method, "_target_columns", None) or ["(unmapped)"]
            raw_description = getattr(method, "_description", None) or (method.__doc__ or "")
            description = " ".join(str(raw_description).split()) if raw_description else rule_id
            severity = getattr(method, "_severity", None)
            test_type = getattr(method, "_test_type", None)

            severity_name = severity.name if hasattr(severity, "name") else str(severity or "ERROR")
            test_type_name = test_type.name if hasattr(test_type, "name") else (str(test_type) if test_type else None)

            for target_column in target_columns:
                signature = (
                    rule_id,
                    str(target_column),
                    description,
                    severity_name,
                    test_type_name,
                )

                # When scanning all packs, inherited/base tests can appear once per pack.
                # Keep one rule row and annotate it with all packs that provide it.
                if not requested_pack and signature in signature_to_rule_index:
                    rule_index = signature_to_rule_index[signature]
                    current_packs = {
                        p.strip() for p in rules[rule_index].pack.split(",") if p.strip()
                    }
                    current_packs.add(pack_name)
                    rules[rule_index].pack = ", ".join(sorted(current_packs))
                    continue

                rules.append(
                    RulesEngineRule(
                        pack=pack_name,
                        rule_id=rule_id,
                        target_column=str(target_column),
                        description=description,
                        severity=severity_name,
                        test_type=test_type_name,
                    )
                )
                if not requested_pack:
                    signature_to_rule_index[signature] = len(rules) - 1

    rules.sort(key=lambda item: (item.target_column.lower(), item.rule_id.lower(), item.pack.lower()))
    return RulesEngineResponse(packs=available_packs, rules=rules)


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
    subscription: Subscription = Depends(enforce_rate_limit),
) -> UsageResponse:
    """Get current usage statistics for your API key."""
    if subscription.metadata.get("is_dev_key"):
        stats = subscription_store.get_usage_stats(subscription.api_key_hash)
    else:
        stats = subscription_service.get_usage_stats(subscription)
    return UsageResponse(**stats)


@app.get("/api/v1/subscription", response_model=SubscriptionInfoResponse)
def get_subscription_info(
    subscription: Subscription = Depends(get_authenticated_subscription),
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
    subscription: Subscription = Depends(enforce_rate_limit),
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,
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
    
    normalized_test_packs: list[str] = []
    seen_packs: set[str] = set()
    for pack_name in payload.testPacks:
        normalized_pack_name = normalize_pack_name(pack_name)
        if not normalized_pack_name or normalized_pack_name in seen_packs:
            continue
        seen_packs.add(normalized_pack_name)
        normalized_test_packs.append(normalized_pack_name)

    normalized_pack_configs: dict[str, dict[str, Any]] = {}
    for pack_name, pack_config in (payload.packConfigs or {}).items():
        normalized_pack_name = normalize_pack_name(pack_name)
        if not normalized_pack_name:
            continue
        existing = dict(normalized_pack_configs.get(normalized_pack_name, {}))
        existing.update(dict(pack_config or {}))
        normalized_pack_configs[normalized_pack_name] = existing

    if normalized_test_packs:
        check_pack_access(subscription, normalized_test_packs)

    effective_pack_configs = dict(normalized_pack_configs)

    # Load persisted per-user/per-sheet/per-pack configs and merge with request config.
    if DB_AVAILABLE and db is not None and not subscription.metadata.get("is_dev_key") and payload.sheetName:
        subscription_user_id = subscription.metadata.get("user_id")
        if subscription_user_id is not None:
            for pack_name in normalized_test_packs:
                stored_config = None
                for variant in get_pack_name_variants(pack_name):
                    stored_config = await pack_config_service.get_config(
                        db,
                        user_id=int(subscription_user_id),
                        sheet_name=payload.sheetName,
                        test_pack=variant,
                    )
                    if stored_config is not None:
                        break

                incoming_pack_config = normalized_pack_configs.get(pack_name, {})
                if stored_config is None:
                    effective_pack_configs[pack_name] = dict(incoming_pack_config or {})
                else:
                    merged_pack_config = dict(stored_config)
                    merged_pack_config.update(dict(incoming_pack_config or {}))
                    effective_pack_configs[pack_name] = merged_pack_config

            # Persist user-provided config updates for this user/sheet/pack.
            if normalized_pack_configs:
                for pack_name, pack_config in normalized_pack_configs.items():
                    if pack_name not in normalized_test_packs:
                        continue
                    await pack_config_service.upsert_config(
                        db,
                        user_id=int(subscription_user_id),
                        sheet_name=payload.sheetName,
                        test_pack=pack_name,
                        pack_config=dict(pack_config or {}),
                        workbook_name=payload.workbookName,
                    )

    try:
        report = validate_grid_with_packs_report(
            addresses=payload.addresses,
            values=payload.values,
            column_rules=payload.columnRules,
            test_packs=normalized_test_packs,
            has_header_row=payload.hasHeaderRow,
            pack_configs=effective_pack_configs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if subscription.metadata.get("is_dev_key"):
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Validation failed in Python backend.",
                    "python_error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc().splitlines(),
                },
            ) from exc
        raise HTTPException(status_code=500, detail="Internal validation error") from exc

    coverage = report.get("coverage") if payload.includeCoverage else None
    
    # Include usage stats in response
    if subscription.metadata.get("is_dev_key"):
        usage = subscription_store.get_usage_stats(subscription.api_key_hash)
    else:
        usage = subscription_service.get_usage_stats(subscription)
    
    # Store results in database
    validation_run_id = None
    if payload.storeResults and DB_AVAILABLE and coverage:
        try:
            async with async_session_maker() as session:
                # Calculate summary stats from coverage
                summary = coverage.get("summary", {})
                
                validation_run = await store_validation_results(
                    session,
                    api_key=None if not subscription.metadata.get("is_dev_key") else subscription.api_key,
                    owner_email=subscription.owner_email if not subscription.metadata.get("is_dev_key") else None,
                    test_packs=normalized_test_packs,
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


@app.get("/api/v1/pack-config", response_model=PackConfigResponse)
async def get_pack_config(
    test_pack: str,
    sheet_name: str,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> PackConfigResponse:
    """Get persisted test-pack config for the authenticated user and sheet."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    if subscription.metadata.get("is_dev_key"):
        raise HTTPException(status_code=400, detail="Pack config persistence requires a database-backed user")

    normalized_pack = normalize_pack_name(test_pack)

    subscription_user_id = subscription.metadata.get("user_id")
    if subscription_user_id is None:
        raise HTTPException(status_code=400, detail="Missing user context")

    async with async_session_maker() as session:
        config = None
        for variant in get_pack_name_variants(normalized_pack):
            config = await pack_config_service.get_config(
                session,
                user_id=int(subscription_user_id),
                sheet_name=sheet_name,
                test_pack=variant,
            )
            if config is not None:
                break

    return PackConfigResponse(
        test_pack=normalized_pack,
        sheet_name=sheet_name,
        pack_config=config or {},
    )


@app.put("/api/v1/pack-config", response_model=PackConfigResponse)
async def upsert_pack_config(
    payload: PackConfigRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> PackConfigResponse:
    """Persist test-pack config for the authenticated user/sheet/pack."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    if subscription.metadata.get("is_dev_key"):
        raise HTTPException(status_code=400, detail="Pack config persistence requires a database-backed user")

    normalized_pack = normalize_pack_name(payload.test_pack)

    subscription_user_id = subscription.metadata.get("user_id")
    if subscription_user_id is None:
        raise HTTPException(status_code=400, detail="Missing user context")

    async with async_session_maker() as session:
        saved_config = await pack_config_service.upsert_config(
            session,
            user_id=int(subscription_user_id),
            sheet_name=payload.sheet_name,
            test_pack=normalized_pack,
            pack_config=payload.pack_config,
            workbook_name=payload.workbook_name,
        )

    return PackConfigResponse(
        test_pack=normalized_pack,
        sheet_name=payload.sheet_name,
        workbook_name=payload.workbook_name,
        pack_config=saved_config,
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
    subscription: Subscription = Depends(get_authenticated_subscription),
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
            owner_email=subscription.owner_email if not subscription.metadata.get("is_dev_key") else None,
            api_key=subscription.api_key if subscription.metadata.get("is_dev_key") else None,
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
    subscription: Subscription = Depends(get_authenticated_subscription),
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
        if subscription.metadata.get("is_dev_key"):
            if run.api_key_hash != subscription.api_key_hash:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            subscription_user_id = subscription.metadata.get("user_id")
            if subscription_user_id is None or run.user_id != int(subscription_user_id):
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
    subscription: Subscription = Depends(get_authenticated_subscription),
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
            owner_email=subscription.owner_email if not subscription.metadata.get("is_dev_key") else None,
            api_key=subscription.api_key if subscription.metadata.get("is_dev_key") else None,
            test_pack=test_pack,
            days=days,
        )
        
        return TestStatisticsResponse(**stats)
