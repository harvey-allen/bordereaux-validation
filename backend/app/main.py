from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from typing import Any, Optional, Union

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import (
    Subscription,
    check_cell_limit,
    check_pack_access,
    get_subscription_allowed_packs,
    subscription_store,
)
from app.testpacks.core import TEST_PACKS, BaseTestPack, get_pack_name_variants, normalize_pack_name
from app.validation import get_pack_territories, get_pack_mandatory_fields, validate_grid_with_packs_report
from app.utils.normalization import UNKNOWN_SHEET, UNKNOWN_WORKBOOK, normalize_scope_value

# Load environment variables
load_dotenv()

# Database imports (optional - gracefully handle if DB not available)
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import (
        get_db, 
        init_db, 
        close_db, 
        async_session_maker,
        ValidationResultVersion,
        UserSubscription,
    )
    from app.subscription_service import subscription_service
    from app.results_service import (
        delete_results_version_by_id,
        delete_results_version,
        get_results_version_payload_by_id,
        get_or_create_sheet_key,
        get_results_version,
        list_results_versions_for_pack,
        remove_exception_tags_from_results,
        get_test_statistics,
        get_validation_history,
        get_validation_run,
        save_results_version,
        store_validation_results,
        update_results_version_by_id,
        upsert_validation_run_tagged_cells,
    )
    from app.pack_config_service import pack_config_service
    from app.exceptions_service import exception_service
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
    storeResults: bool = Field(default=True, description="Store per-run test summaries in test_results")
    workbookName: Optional[str] = Field(default=None, description="Name of the workbook being validated")
    sheetName: Optional[str] = Field(default=None, description="Name of the sheet being validated")
    rangeAddress: Optional[str] = Field(default=None, description="Address of the range being validated")


class ValidateResponse(BaseModel):
    results: list[dict[str, Any]]
    coverage: Optional[dict[str, Any]] = None
    usage: Optional[dict[str, Any]] = None
    validation_run_id: Optional[int] = None


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
    test_type: Optional[str] = None


class RulesEngineResponse(BaseModel):
    packs: list[str]
    rules: list[RulesEngineRule]


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
    title="Reporting Validation API",
    version="1.0.0",
    description="Excel data validation API for configurable reporting test packs with subscription-based access.",
    lifespan=lifespan,
)


class TestPackCatalogResponse(BaseModel):
    all_packs: list[str]
    allowed_packs: Optional[list[str]]
    default_pack: Optional[str]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _require_db_backed_user(subscription: Subscription) -> tuple[int, int]:
    """Return (user_id, organisation_id) for DB-backed users, else raise 400."""
    if subscription.metadata.get("is_dev_key"):
        raise HTTPException(status_code=400, detail="This endpoint requires a database-backed user")

    user_id = subscription.metadata.get("user_id")
    organisation_id = subscription.metadata.get("organisation_id")
    if user_id is None or organisation_id is None:
        raise HTTPException(status_code=400, detail="Missing user context")

    return int(user_id), int(organisation_id)


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


@app.get("/api/v1/generate-template", response_model=TemplateResponse)
def generate_template(test_pack: str, territory: Optional[str] = None) -> TemplateResponse:
    """Generate a template with field headers for the given test pack and territory."""
    normalized_pack = normalize_pack_name(test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    # Get available territories if none specified
    territories = get_pack_territories(normalized_pack)
    if not territories:
        raise HTTPException(status_code=400, detail=f"No territories found for test pack '{normalized_pack}'")

    # Use first territory if none specified
    selected_territory = territory or territories[0]

    # Get mandatory fields for the pack and territory
    headers = get_pack_mandatory_fields(normalized_pack, selected_territory)
    
    if not headers:
        raise HTTPException(
            status_code=400, 
            detail=f"No mandatory fields found for test pack '{normalized_pack}' and territory '{selected_territory}'"
        )

    return TemplateResponse(
        test_pack=normalized_pack,
        territory=selected_territory,
        headers=headers,
        total_fields=len(headers),
    )


@app.post("/api/v1/field-config/estimate-mapping", response_model=FieldMappingEstimationResponse)
async def estimate_field_mapping(
    request: FieldMappingEstimationRequest,
    subscription: Subscription = Depends(enforce_rate_limit),
) -> FieldMappingEstimationResponse:
    """Estimate field mapping from uploaded column headers to schema fields using fuzzy matching."""
    normalized_pack = normalize_pack_name(request.test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    if not request.territory or not request.territory.strip():
        raise HTTPException(status_code=400, detail="territory is required")

    if not request.headers or len(request.headers) == 0:
        raise HTTPException(status_code=400, detail="headers list cannot be empty")

    # Verify access
    check_pack_access(subscription, [normalized_pack])

    # Get mandatory and conditional fields for the pack and territory
    mandatory_fields = get_pack_mandatory_fields(normalized_pack, request.territory)
    
    # Import the estimator function
    from app.pack_config_service import estimate_field_mapping as backend_estimate_field_mapping
    
    result = await backend_estimate_field_mapping(
        test_pack=normalized_pack,
        territory=request.territory,
        headers=request.headers,
        mandatory_fields=mandatory_fields,
    )

    return FieldMappingEstimationResponse(
        test_pack=normalized_pack,
        territory=request.territory,
        estimated_mappings=result["estimated_mappings"],
        matched_count=result["matched_count"],
        unmatched_headers=result["unmatched_headers"],
        unmatched_fields=result["unmatched_fields"],
        confidence_summary=result["confidence_summary"],
    )


@app.get("/api/v1/rules-engine", response_model=RulesEngineResponse)
def get_rules_engine_rules(test_pack: Optional[str] = None) -> RulesEngineResponse:
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
    signature_to_rule_index: dict[tuple[str, str, str, str, Optional[str]], int] = {}

    for pack_name in packs_to_scan:
        pack_cls = TEST_PACKS.get(pack_name)
        if pack_cls is None:
            continue

        if not issubclass(pack_cls, BaseTestPack):
            continue

        for metadata in pack_cls.collect_registered_tests():
            severity_name = metadata.severity.name
            test_type_name = metadata.test_type.name if metadata.test_type else None

            for target_column in metadata.target_columns:
                signature = (
                    metadata.rule_id,
                    str(target_column),
                    metadata.description,
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
                        rule_id=metadata.rule_id,
                        target_column=str(target_column),
                        description=metadata.description,
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
        organisation_name=request.organisation_name,
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
    allowed_packs = get_subscription_allowed_packs(subscription)
    return SubscriptionInfoResponse(
        tier=subscription.tier.value,
        owner_email=subscription.owner_email,
        display_name=(subscription.metadata.get("display_name") or None),
        is_active=subscription.is_active,
        expires_at=subscription.expires_at.isoformat() if subscription.expires_at else None,
        allowed_packs=allowed_packs,
        max_cells_per_request=subscription.config.max_cells_per_request,
    )


@app.get("/api/v1/test-packs", response_model=TestPackCatalogResponse)
def get_test_pack_catalog(
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> TestPackCatalogResponse:
    """Return all packs plus the packs available for the authenticated subscription."""
    all_packs = sorted(TEST_PACKS.keys())
    allowed = get_subscription_allowed_packs(subscription)

    if allowed is None:
        effective_allowed = all_packs
    else:
        allowed_set = set(allowed)
        effective_allowed = [pack_name for pack_name in all_packs if pack_name in allowed_set]

    default_pack = effective_allowed[0] if effective_allowed else None

    return TestPackCatalogResponse(
        all_packs=all_packs,
        allowed_packs=effective_allowed,
        default_pack=default_pack,
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

    unknown_packs = [pack_name for pack_name in normalized_test_packs if pack_name not in TEST_PACKS]
    if unknown_packs:
        unique_unknown = ", ".join(sorted(set(unknown_packs)))
        raise HTTPException(status_code=400, detail=f"Unknown test pack(s): {unique_unknown}")

    if normalized_test_packs:
        check_pack_access(subscription, normalized_test_packs)

    effective_pack_configs = dict(normalized_pack_configs)

    # Load persisted per-user/per-sheet/per-pack configs and merge with request config.
    if DB_AVAILABLE and db is not None and not subscription.metadata.get("is_dev_key") and payload.sheetName:
        subscription_user_id = subscription.metadata.get("user_id")
        organisation_id = subscription.metadata.get("organisation_id")
        if subscription_user_id is not None and organisation_id is not None:
            for pack_name in normalized_test_packs:
                stored_config = None
                for variant in get_pack_name_variants(pack_name):
                    stored_config = await pack_config_service.get_config(
                        db,
                        organisation_id=int(organisation_id),
                        user_id=int(subscription_user_id),
                        workbook_name=payload.workbookName,
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
                        organisation_id=int(organisation_id),
                        user_id=int(subscription_user_id),
                        workbook_name=payload.workbookName,
                        sheet_name=payload.sheetName,
                        test_pack=pack_name,
                        pack_config=dict(pack_config or {}),
                    )

    try:
        report = validate_grid_with_packs_report(
            addresses=payload.addresses,
            values=payload.values,
            column_rules=payload.columnRules,
            test_packs=payload.testPacks,
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
    workbook_name: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> PackConfigResponse:
    """Get persisted test-pack config for the authenticated user and sheet."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    normalized_pack = normalize_pack_name(test_pack)

    async with async_session_maker() as session:
        config = None
        for variant in get_pack_name_variants(normalized_pack):
            config = await pack_config_service.get_config(
                session,
                organisation_id=organisation_id,
                user_id=user_id,
                workbook_name=workbook_name,
                sheet_name=sheet_name,
                test_pack=variant,
            )
            if config is not None:
                break

    return PackConfigResponse(
        test_pack=normalized_pack,
        sheet_name=sheet_name,
        workbook_name=workbook_name,
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
    user_id, organisation_id = _require_db_backed_user(subscription)

    normalized_pack = normalize_pack_name(payload.test_pack)

    async with async_session_maker() as session:
        saved_config = await pack_config_service.upsert_config(
            session,
            organisation_id=organisation_id,
            user_id=user_id,
            workbook_name=payload.workbook_name,
            sheet_name=payload.sheet_name,
            test_pack=normalized_pack,
            pack_config=payload.pack_config,
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


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_version_kpis(results_json: dict[str, Any]) -> VersionKpiSummary:
    kpis_from_json = results_json.get("KPIs") if isinstance(results_json, dict) else {}
    if not isinstance(kpis_from_json, dict):
        kpis_from_json = {}

    summary_metrics = results_json.get("summary_metrics") if isinstance(results_json, dict) else {}
    if not isinstance(summary_metrics, dict):
        summary_metrics = {}

    failed_items = results_json.get("failed") if isinstance(results_json, dict) else []
    failed_items = failed_items if isinstance(failed_items, list) else []
    passed_tests = results_json.get("passed_tests") if isinstance(results_json, dict) else []
    passed_tests = passed_tests if isinstance(passed_tests, list) else []
    passed_umrs = results_json.get("passed_umrs") if isinstance(results_json, dict) else []
    passed_umrs = passed_umrs if isinstance(passed_umrs, list) else []

    failed_submission_ids: set[str] = set()
    failed_test_ids: set[str] = set()
    for item in failed_items:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("id") or item.get("umr") or "").strip()
        if row_id:
            failed_submission_ids.add(row_id)
        for test_id in (item.get("tests") or []):
            text_id = str(test_id or "").strip()
            if text_id:
                failed_test_ids.add(text_id)

    submissions_failed = len(failed_submission_ids)
    tests_failed = len(failed_test_ids)

    submissions_failed = _to_int(kpis_from_json.get("submissions_failed")) if kpis_from_json else submissions_failed
    if submissions_failed is None:
        submissions_failed = len(failed_submission_ids)

    tests_failed = _to_int(kpis_from_json.get("tests_failed")) if kpis_from_json else tests_failed
    if tests_failed is None:
        tests_failed = len(failed_test_ids)

    total_submissions = _to_int(kpis_from_json.get("total_submissions"))
    if total_submissions is None:
        total_submissions = _to_int(summary_metrics.get("total_submissions"))
    if total_submissions is None:
        total_submissions = len(failed_submission_ids.union({str(v).strip() for v in passed_umrs if str(v).strip()}))

    total_tests = _to_int(kpis_from_json.get("total_tests"))
    if total_tests is None:
        total_tests = _to_int(summary_metrics.get("total_tests"))
    if total_tests is None:
        total_tests = len(failed_test_ids.union({str(v).strip() for v in passed_tests if str(v).strip()}))

    submissions_failed_pct = _to_float(kpis_from_json.get("submissions_failed_pct"))
    if submissions_failed_pct is None:
        submissions_failed_pct = ((submissions_failed / total_submissions) * 100) if total_submissions else None

    tests_failed_pct = _to_float(kpis_from_json.get("tests_failed_pct"))
    if tests_failed_pct is None:
        tests_failed_pct = ((tests_failed / total_tests) * 100) if total_tests else None

    tests_passed_pct = _to_float(kpis_from_json.get("tests_passed_pct"))
    if tests_passed_pct is None:
        tests_passed_pct = ((1 - (tests_failed / total_tests)) * 100) if total_tests else None

    fields_failed = _to_int(kpis_from_json.get("fields_failed"))
    if fields_failed is None:
        fields_failed = _to_int(summary_metrics.get("fields_failed"))

    total_fields = _to_int(kpis_from_json.get("total_fields"))
    if total_fields is None:
        total_fields = _to_int(summary_metrics.get("total_fields"))

    fields_failed_pct = _to_float(kpis_from_json.get("fields_failed_pct"))
    if fields_failed_pct is None:
        fields_failed_pct = ((fields_failed / total_fields) * 100) if fields_failed is not None and total_fields else None

    return VersionKpiSummary(
        submissions_failed=submissions_failed,
        submissions_failed_pct=submissions_failed_pct,
        fields_failed=fields_failed,
        fields_failed_pct=fields_failed_pct,
        tests_failed=tests_failed,
        tests_failed_pct=tests_failed_pct,
        tests_passed_pct=tests_passed_pct,
    )


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
            for pack_name, pack_data in (run.coverage_json or {}).items():
                for test_name, test_data in (pack_data.get("tests") or {}).items():
                    tests.append({
                        "test_pack": pack_name,
                        "test_name": test_name,
                        "description": test_data.get("description"),
                        "severity": test_data.get("severity"),
                        "evaluated_rows": int(test_data.get("evaluatedRows", 0)),
                        "passed_rows": int(test_data.get("passedRows", 0)),
                        "failed_rows": int(test_data.get("failedRows", 0)),
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
                tagged_cells=list(run.tagged_cells_json or []),
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
        for pack_name, pack_data in (run.coverage_json or {}).items():
            for test_name, test_data in (pack_data.get("tests") or {}).items():
                tests.append({
                    "test_pack": pack_name,
                    "test_name": test_name,
                    "description": test_data.get("description"),
                    "target_columns": test_data.get("targetColumns", []),
                    "severity": test_data.get("severity"),
                    "severity_weight": test_data.get("severityWeight"),
                    "evaluated_rows": int(test_data.get("evaluatedRows", 0)),
                    "passed_rows": int(test_data.get("passedRows", 0)),
                    "failed_rows": int(test_data.get("failedRows", 0)),
                    "failed_refs": test_data.get("failedRefs"),
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
            "tagged_cells": list(run.tagged_cells_json or []),
            "tests": tests,
        }


@app.get("/api/v1/statistics", response_model=TestStatisticsResponse)
async def get_statistics(
    days: int = 30,
    test_pack: Optional[str] = None,
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


@app.post("/api/v1/results/versions", response_model=SavedResultsVersionItem)
async def save_results(
    payload: SaveResultsVersionRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> SavedResultsVersionItem:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    resolved_pack_name = payload.test_pack
    if not resolved_pack_name:
        if isinstance(payload.test_packs, list):
            resolved_pack_name = payload.test_packs[0] if payload.test_packs else None
        else:
            resolved_pack_name = payload.test_packs

    normalized_pack = normalize_pack_name(resolved_pack_name)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    async with async_session_maker() as session:
        saved = await save_results_version(
            session,
            organisation_id=organisation_id,
            user_id=user_id,
            workbook_name=payload.workbook_name,
            sheet_name=payload.sheet_name,
            test_pack=normalized_pack,
            failed_tests=[{"umr": item.umr_or_id, "id": item.umr_or_id, "test_id": item.test_id} for item in payload.failed_tests],
            passed_tests=payload.passed_tests,
            passed_umrs=payload.passed_umrs,
            mapped_headers=payload.mapped_headers,
            saved_data=payload.saved_data,
            tagged_cells=payload.tagged_cells,
            version_name=payload.version_name,
            kpis=dict(payload.kpis or payload.summary_metrics or {}),
        )
        saved_version_name = str(getattr(saved, "version_name", "") or "").strip() or None
        if saved_version_name is None and isinstance(saved.results_json, dict):
            saved_version_name = str(saved.results_json.get("version_name") or "").strip() or None
        return SavedResultsVersionItem(
            id=saved.id,
            created_at=saved.created_at.isoformat(),
            updated_at=saved.updated_at.isoformat(),
            version_name=saved_version_name,
        )


@app.post("/api/v1/exceptions/apply")
async def apply_exception_tag(
    payload: ExceptionApplyRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> dict[str, Any]:
    """Persist exception tags for the latest validation run in the current workbook/sheet scope."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    if not payload.sheet_name.strip():
        raise HTTPException(status_code=400, detail="sheet_name is required")

    normalized_pack = normalize_pack_name(payload.test_pack) if payload.test_pack else None
    tagged_cells_from_payload = []
    for item in payload.tagged_cells or []:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or "").strip().upper()
        if not address:
            continue
        tagged_cells_from_payload.append(
            {
                "address": address,
                "exception_id": payload.exception_id,
                "comment": str(item.get("comment") or f"Exception tagged: {payload.exception_id}").strip(),
                "fill_color": str(item.get("fill_color") or item.get("fillColor") or "#dbeafe").strip() or "#dbeafe",
                "previous_fill_color": str(item.get("previous_fill_color") or item.get("previousFillColor") or "").strip(),
                "sheet_name": str(item.get("sheet_name") or item.get("sheetName") or payload.sheet_name).strip(),
                "workbook_name": str(item.get("workbook_name") or item.get("workbookName") or payload.workbook_name or "").strip(),
                "tagged_at": str(item.get("tagged_at") or item.get("taggedAt") or "").strip(),
            }
        )

    fallback_tagged_cells = [
        {
            "address": str(address or "").strip().upper(),
            "exception_id": payload.exception_id,
            "comment": f"Exception tagged: {payload.exception_id}",
            "fill_color": "#dbeafe",
            "previous_fill_color": "",
            "sheet_name": payload.sheet_name,
            "workbook_name": payload.workbook_name,
        }
        for address in payload.addresses
        if str(address or "").strip()
    ]

    tagged_cells = tagged_cells_from_payload or fallback_tagged_cells
    if not tagged_cells:
        raise HTTPException(status_code=400, detail="At least one address is required")

    async with async_session_maker() as session:
        run = await upsert_validation_run_tagged_cells(
            session,
            organisation_id=organisation_id,
            user_id=user_id,
            workbook_name=payload.workbook_name,
            sheet_name=payload.sheet_name,
            test_pack=normalized_pack,
            tagged_cells=tagged_cells,
        )
        return {
            "updated": True,
            "run_id": run.id,
            "tagged_cells": list(run.tagged_cells_json or []),
        }


@app.get("/api/v1/results/versions", response_model=SavedResultsVersionListResponse)
async def get_result_versions(
    sheet_name: str,
    test_pack: str,
    workbook_name: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> SavedResultsVersionListResponse:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        normalized_pack = normalize_pack_name(test_pack)
        if not normalized_pack:
            raise HTTPException(status_code=400, detail="test_pack is required")

        current_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
        current_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)

        versions_with_scope = await list_results_versions_for_pack(
            session,
            organisation_id=organisation_id,
            test_pack=normalized_pack,
        )

        items: list[SavedResultsVersionItem] = []
        for entry in versions_with_scope:
            version = entry.version
            version_name = (str(getattr(version, "version_name", "") or "").strip() or None)
            if version_name is None and isinstance(version.results_json, dict):
                version_name = str(version.results_json.get("version_name") or "").strip() or None

            is_current_scope = (
                str(entry.workbook_name or "").strip() == current_workbook
                and str(entry.sheet_name or "").strip() == current_sheet
            )

            items.append(
                SavedResultsVersionItem(
                    id=version.id,
                    created_at=version.created_at.isoformat(),
                    updated_at=version.updated_at.isoformat(),
                    version_name=version_name,
                    workbook_name=entry.workbook_name,
                    sheet_name=entry.sheet_name,
                    current_scope=is_current_scope,
                )
            )

        items.sort(key=lambda item: (0 if item.current_scope else 1, item.updated_at), reverse=False)
        current_items = [item for item in items if item.current_scope]
        other_items = [item for item in items if not item.current_scope]
        current_items.sort(key=lambda item: item.updated_at, reverse=True)
        other_items.sort(key=lambda item: item.updated_at, reverse=True)

        return SavedResultsVersionListResponse(versions=[*current_items, *other_items])


@app.get("/api/v1/results/latest", response_model=LatestResultsVersionResponse)
async def get_latest_results(
    sheet_name: str,
    test_pack: str,
    workbook_name: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> LatestResultsVersionResponse:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        normalized_pack = normalize_pack_name(test_pack)
        if not normalized_pack:
            raise HTTPException(status_code=400, detail="test_pack is required")

        latest = await get_results_version(
            session,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=normalized_pack,
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="No saved result versions found")

        return LatestResultsVersionResponse(
            id=latest.id,
            created_at=latest.created_at.isoformat(),
            updated_at=latest.updated_at.isoformat(),
            workbook_name=normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK),
            sheet_name=normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET),
            version_name=(str(getattr(latest, "version_name", "") or "").strip() or None)
            or ((str(latest.results_json.get("version_name") or "").strip() if isinstance(latest.results_json, dict) else None) or None),
            results=dict(latest.results_json or {}),
        )


@app.get("/api/v1/results/versions/{version_id:int}", response_model=SavedResultsVersionPayloadResponse)
async def get_result_version_payload(
    version_id: int,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> SavedResultsVersionPayloadResponse:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        payload = await get_results_version_payload_by_id(
            session,
            organisation_id=organisation_id,
            user_id=user_id,
            version_id=version_id,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="Saved result version not found")
        return SavedResultsVersionPayloadResponse(**payload)


@app.get("/api/v1/results/versions/comparison", response_model=VersionComparisonResponse)
async def get_result_versions_comparison(
    sheet_name: str,
    test_pack: str,
    workbook_name: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> VersionComparisonResponse:
    if not DB_AVAILABLE:  # static route — must stay above /{version_id}
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    normalized_pack = normalize_pack_name(test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    current_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
    current_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)

    async with async_session_maker() as session:
        saved_versions = await list_results_versions_for_pack(
            session,
            organisation_id=organisation_id,
            test_pack=normalized_pack,
        )

        trend_items: list[VersionTrendPoint] = []
        previous_version: Optional[PreviousVersionSummary] = None

        for item in sorted(saved_versions, key=lambda v: v.version.created_at):
            kpis = _build_version_kpis(dict(item.version.results_json or {}))
            trend_version_name = (str(getattr(item.version, "version_name", "") or "").strip() or None)
            if trend_version_name is None and isinstance(item.version.results_json, dict):
                trend_version_name = str(item.version.results_json.get("version_name") or "").strip() or None
            trend_items.append(
                VersionTrendPoint(
                    id=item.version.id,
                    workbook_name=item.workbook_name,
                    sheet_name=item.sheet_name,
                    created_at=item.version.created_at.isoformat(),
                    updated_at=item.version.updated_at.isoformat(),
                    version_name=trend_version_name,
                    test_passed_pct=kpis.tests_passed_pct,
                    submissions_failed_pct=kpis.submissions_failed_pct,
                    fields_failed_pct=kpis.fields_failed_pct,
                )
            )

        for item in saved_versions:
            same_scope = item.workbook_name == current_workbook and item.sheet_name == current_sheet
            if same_scope:
                continue

            kpis = _build_version_kpis(dict(item.version.results_json or {}))
            previous_version = PreviousVersionSummary(
                id=item.version.id,
                workbook_name=item.workbook_name,
                sheet_name=item.sheet_name,
                created_at=item.version.created_at.isoformat(),
                updated_at=item.version.updated_at.isoformat(),
                version_name=(str(getattr(item.version, "version_name", "") or "").strip() or None)
                or ((str(item.version.results_json.get("version_name") or "").strip() if isinstance(item.version.results_json, dict) else None) or None),
                kpis=kpis,
            )
            break

        return VersionComparisonResponse(previous_version=previous_version, trend=trend_items)


@app.put("/api/v1/results/versions/{version_id:int}", response_model=SavedResultsVersionItem)
async def update_result_version_by_id_endpoint(
    version_id: int,
    payload: SaveResultsVersionRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> SavedResultsVersionItem:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    resolved_pack_name = payload.test_pack
    if not resolved_pack_name:
        if isinstance(payload.test_packs, list):
            resolved_pack_name = payload.test_packs[0] if payload.test_packs else None
        else:
            resolved_pack_name = payload.test_packs

    normalized_pack = normalize_pack_name(resolved_pack_name)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    async with async_session_maker() as session:
        try:
            saved = await update_results_version_by_id(
                session,
                organisation_id=organisation_id,
                user_id=user_id,
                version_id=version_id,
                test_pack=normalized_pack,
                failed_tests=[{"umr": item.umr_or_id, "id": item.umr_or_id, "test_id": item.test_id} for item in payload.failed_tests],
                passed_tests=payload.passed_tests,
                passed_umrs=payload.passed_umrs,
                mapped_headers=payload.mapped_headers,
                saved_data=payload.saved_data,
                tagged_cells=payload.tagged_cells,
                version_name=payload.version_name,
                kpis=dict(payload.kpis or payload.summary_metrics or {}),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if saved is None:
            raise HTTPException(status_code=404, detail="Saved result version not found")

        saved_version_name = str(getattr(saved, "version_name", "") or "").strip() or None
        if saved_version_name is None and isinstance(saved.results_json, dict):
            saved_version_name = str(saved.results_json.get("version_name") or "").strip() or None
        return SavedResultsVersionItem(
            id=saved.id,
            created_at=saved.created_at.isoformat(),
            updated_at=saved.updated_at.isoformat(),
            version_name=saved_version_name,
        )


@app.delete("/api/v1/results/versions")
async def remove_result_version(
    sheet_name: str,
    test_pack: str,
    workbook_name: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> dict[str, Any]:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    normalized_pack = normalize_pack_name(test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    async with async_session_maker() as session:
        sheet_key = await get_or_create_sheet_key(
            session,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=normalized_pack,
        )
        deleted = await delete_results_version(
            session,
            organisation_id=organisation_id,
            sheet_key_id=int(sheet_key.id),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved result version not found")
        return {"deleted": True, "sheet_key_id": sheet_key.id}


@app.delete("/api/v1/results/versions/{version_id:int}")
async def remove_result_version_by_id(
    version_id: int,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> dict[str, Any]:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        deleted = await delete_results_version_by_id(
            session,
            organisation_id=organisation_id,
            version_id=version_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved result version not found")
        return {"deleted": True, "version_id": version_id}


# ============================================================================
# EXCEPTION MANAGEMENT ENDPOINTS
# ============================================================================


@app.get("/api/v1/exceptions", response_model=ExceptionListResponse)
async def list_exceptions(
    linked_field: Optional[str] = None,
    linked_umr: Optional[str] = None,
    test_id: Optional[str] = None,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> ExceptionListResponse:
    """List all exceptions for the authenticated user's organisation."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        exceptions = await exception_service.get_exceptions(
            session,
            organisation_id=organisation_id,
            linked_field=linked_field,
            linked_umr=linked_umr,
            test_id=test_id,
        )
        
        items = [
            ExceptionItem(
                id=exc.id,
                exception_id=exc.exception_id,
                linked_field=exc.linked_field,
                linked_umr=exc.linked_umr,
                test_id=exc.linked_field,
                description=exc.description,
                status=exc.status,
                author_id=exc.author_id,
                created_at=exc.created_at.isoformat(),
                updated_at=exc.updated_at.isoformat(),
            )
            for exc in exceptions
        ]
        return ExceptionListResponse(exceptions=items)


@app.post("/api/v1/exceptions", response_model=ExceptionItem)
async def create_exception(
    request: ExceptionCreateRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> ExceptionItem:
    """Create a new exception."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        # Check for duplicate exception_id within organisation
        existing = await exception_service.get_exception_by_id(
            session,
            organisation_id=organisation_id,
            exception_id=request.exception_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Exception '{request.exception_id}' already exists in this organisation",
            )
        
        exc = await exception_service.create_exception(
            session,
            organisation_id=organisation_id,
            exception_id=request.exception_id,
            description=request.description,
            linked_field=(request.linked_field or request.test_id),
            linked_umr=request.linked_umr,
            test_id=request.test_id,
            status=request.status,
            author_id=user_id,
        )
        await session.commit()
        
        return ExceptionItem(
            id=exc.id,
            exception_id=exc.exception_id,
            linked_field=exc.linked_field,
            linked_umr=exc.linked_umr,
            test_id=exc.linked_field,
            description=exc.description,
            status=exc.status,
            author_id=exc.author_id,
            created_at=exc.created_at.isoformat(),
            updated_at=exc.updated_at.isoformat(),
        )


@app.put("/api/v1/exceptions/{exception_id}", response_model=ExceptionItem)
async def update_exception(
    exception_id: str,
    request: ExceptionUpdateRequest,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> ExceptionItem:
    """Update an existing exception."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        exc = await exception_service.update_exception(
            session,
            organisation_id=organisation_id,
            exception_id=exception_id,
            description=request.description,
            linked_field=(request.linked_field if "linked_field" in request.model_fields_set else request.test_id),
            linked_umr=request.linked_umr,
            test_id=request.test_id,
            update_linked_field=("linked_field" in request.model_fields_set or "test_id" in request.model_fields_set),
            update_linked_umr=("linked_umr" in request.model_fields_set),
            status=request.status,
        )
        if not exc:
            raise HTTPException(status_code=404, detail="Exception not found")
        
        await session.commit()
        
        return ExceptionItem(
            id=exc.id,
            exception_id=exc.exception_id,
            linked_field=exc.linked_field,
            linked_umr=exc.linked_umr,
            test_id=exc.linked_field,
            description=exc.description,
            status=exc.status,
            author_id=exc.author_id,
            created_at=exc.created_at.isoformat(),
            updated_at=exc.updated_at.isoformat(),
        )


@app.delete("/api/v1/exceptions/{exception_id}")
async def delete_exception(
    exception_id: str,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> dict[str, Any]:
    """Delete an exception."""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        existing_exception = await exception_service.get_exception_by_id(
            session,
            organisation_id=organisation_id,
            exception_id=exception_id,
        )
        if not existing_exception:
            raise HTTPException(status_code=404, detail="Exception not found")

        tag_cleanup_result = await remove_exception_tags_from_results(
            session,
            organisation_id=organisation_id,
            exception_id=exception_id,
        )

        deleted = await exception_service.delete_exception(
            session,
            organisation_id=organisation_id,
            exception_id=exception_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Exception not found")
        
        await session.commit()
        return {
            "deleted": True,
            "exception_id": exception_id,
            "tags_removed": int(tag_cleanup_result.get("tags_removed", 0) or 0),
            "runs_updated": int(tag_cleanup_result.get("runs_updated", 0) or 0),
            "versions_updated": int(tag_cleanup_result.get("versions_updated", 0) or 0),
            "removed_tagged_cells": list(tag_cleanup_result.get("removed_tagged_cells") or []),
        }


class ExceptionAnalyticsItem(BaseModel):
    """Exception with tag count for analytics visualization."""
    exception_id: str
    description: str
    tag_count: int
    status: str


class ExceptionAnalyticsResponse(BaseModel):
    """Response for exception analytics endpoint."""
    analytics: list[ExceptionAnalyticsItem]


@app.get("/api/v1/exceptions/analytics", response_model=ExceptionAnalyticsResponse)
async def get_exception_analytics(
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> ExceptionAnalyticsResponse:
    """
    Get exception analytics showing exception IDs and tag counts.
    
    Returns all exceptions for the organisation with the count of tags
    (cells) associated with each exception, sorted by tag count descending.
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    _, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        # Get all exceptions for the organisation
        exceptions = await exception_service.get_exceptions(
            session,
            organisation_id=organisation_id,
        )
        
        # For each exception, count tags across all validation runs and result versions
        # by looking at tagged_cells_json arrays
        exception_tag_counts = {}
        
        # Query all validation result versions for this organisation
        from sqlalchemy import select
        
        # First get all user IDs in this organisation
        user_id_query = select(UserSubscription.id).where(
            UserSubscription.organisation_id == organisation_id
        )
        user_result = await session.execute(user_id_query)
        user_ids = [row[0] for row in user_result.fetchall()]
        
        # Then get all validation result versions for those users
        if user_ids:
            versions_query = select(ValidationResultVersion).where(
                ValidationResultVersion.user_id.in_(user_ids)
            )
            versions_result = await session.execute(versions_query)
            versions = versions_result.scalars().all()
        else:
            versions = []
        
        # Count tags per exception_id from tagged_cells_json in result versions
        for version in versions:
            tagged_cells = version.tagged_cells_json or []
            if isinstance(tagged_cells, list):
                for tagged_cell in tagged_cells:
                    if isinstance(tagged_cell, dict):
                        exc_id = str(tagged_cell.get("exception_id") or "").strip()
                        if exc_id:
                            exception_tag_counts[exc_id] = exception_tag_counts.get(exc_id, 0) + 1
        
        # Also count tags from validation runs
        if user_ids:
            from app.database import ValidationRun
            runs_query = select(ValidationRun).where(
                ValidationRun.user_id.in_(user_ids)
            )
            runs_result = await session.execute(runs_query)
            runs = runs_result.scalars().all()
        else:
            runs = []
        
        # Count tags from runs
        for run in runs:
            tagged_cells = run.tagged_cells_json or []
            if isinstance(tagged_cells, list):
                for tagged_cell in tagged_cells:
                    if isinstance(tagged_cell, dict):
                        exc_id = str(tagged_cell.get("exception_id") or "").strip()
                        if exc_id:
                            exception_tag_counts[exc_id] = exception_tag_counts.get(exc_id, 0) + 1
        
        # Build response items
        items = []
        for exc in exceptions:
            tag_count = exception_tag_counts.get(exc.exception_id, 0)
            items.append(
                ExceptionAnalyticsItem(
                    exception_id=exc.exception_id,
                    description=exc.description,
                    tag_count=tag_count,
                    status=exc.status,
                )
            )
        
        # Sort by tag_count descending
        items.sort(key=lambda x: x.tag_count, reverse=True)
        
        return ExceptionAnalyticsResponse(analytics=items)

