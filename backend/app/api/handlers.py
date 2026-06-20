from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException

from app.schemas.validation import ValidateRequest, ValidateResponse
from app.schemas.configuration import (
    FieldMappingEstimationRequest,
    FieldMappingEstimationResponse,
    PackConfigRequest,
    PackConfigResponse,
    TemplateResponse,
    TerritoryOptionsResponse,
)
from app.schemas.subscription import (
    RegisterRequest,
    RegisterResponse,
    SubscriptionInfoResponse,
    TestPackCatalogResponse,
    UsageResponse,
)
from app.schemas.rules_engine import RulesEngineResponse
from app.schemas.results import (
    LatestResultsVersionResponse,
    SavedResultsVersionItem,
    SavedResultsVersionListResponse,
    SavedResultsVersionPayloadResponse,
    SaveResultsVersionRequest,
    TestStatisticsResponse,
    ValidationHistoryItem,
    ValidationHistoryResponse,
    VersionComparisonResponse,
)
from app.schemas.exceptions import (
    ExceptionAnalyticsItem,
    ExceptionAnalyticsResponse,
    ExceptionApplyRequest,
    ExceptionCreateRequest,
    ExceptionItem,
    ExceptionListResponse,
    ExceptionUpdateRequest,
)

from app.auth import (
    Subscription,
    check_cell_limit,
    check_pack_access,
    get_subscription_allowed_packs,
    subscription_store,
)
from app.common.auth.dependencies import enforce_rate_limit, get_authenticated_subscription
from app.services.configuration.field_mapping_service import field_mapping_service
from app.services.exceptions.exception_service import exception_tagging_service
from app.services.results.results_service import results_domain_service
from app.services.rules_engine.rules_engine_service import rules_engine_service
from app.services.validation.validation_orchestration_service import validation_orchestration_service
from app.testpacks.core import TEST_PACKS, get_pack_name_variants, normalize_pack_name
from app.validation import get_pack_territories, get_pack_mandatory_fields, validate_grid_with_packs_report
from app.common.utilities.normalization import UNKNOWN_SHEET, UNKNOWN_WORKBOOK, normalize_scope_value

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
    from app.services.subscription.subscription_service import subscription_service
    from app.services.results.results_persistence_service import (
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
    from app.services.results.report_storage_service import (
        ReportObjectNotFoundError,
        ReportPayloadFormatError,
        ReportStorageConfigurationError,
        ReportStorageError,
    )
    from app.services.configuration.pack_config_service import pack_config_service
    from app.services.exceptions.exception_management_service import exception_service
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


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






def _require_db_backed_user(subscription: Subscription) -> tuple[int, int]:
    """Return (user_id, organisation_id) for DB-backed users, else raise 400."""
    if subscription.metadata.get("is_dev_key"):
        raise HTTPException(status_code=400, detail="This endpoint requires a database-backed user")

    user_id = subscription.metadata.get("user_id")
    organisation_id = subscription.metadata.get("organisation_id")
    if user_id is None or organisation_id is None:
        raise HTTPException(status_code=400, detail="Missing user context")

    return int(user_id), int(organisation_id)


def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "db_available": str(DB_AVAILABLE)}


def get_field_config_territories(test_pack: str) -> TerritoryOptionsResponse:
    """Return available territory options for the given test pack."""
    normalized_pack = normalize_pack_name(test_pack)
    if not normalized_pack:
        raise HTTPException(status_code=400, detail="test_pack is required")

    territories = get_pack_territories(normalized_pack)
    return TerritoryOptionsResponse(test_pack=normalized_pack, territories=territories)


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
    
    result = await field_mapping_service.estimate_field_mapping(
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


def get_rules_engine_rules(test_pack: Optional[str] = None) -> RulesEngineResponse:
    """Return test-pack rules for the Rules Engine UI."""
    try:
        return rules_engine_service.get_rules(test_pack=test_pack)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def get_usage(
    subscription: Subscription = Depends(enforce_rate_limit),
) -> UsageResponse:
    """Get current usage statistics for your API key."""
    if subscription.metadata.get("is_dev_key"):
        stats = subscription_store.get_usage_stats(subscription.api_key_hash)
    else:
        stats = subscription_service.get_usage_stats(subscription)
    return UsageResponse(**stats)


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
    
    try:
        normalized_test_packs, effective_pack_configs = await validation_orchestration_service.build_effective_pack_configs(
            payload=payload,
            subscription=subscription,
            db_available=DB_AVAILABLE,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        try:
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
                worksheet_snapshot=payload.worksheet_snapshot,
                excel_file_base64=payload.excel_file_base64,
                excel_source_sheet_name=payload.excel_source_sheet_name,
                tagged_cells=payload.tagged_cells,
                version_name=payload.version_name,
                kpis=dict(payload.kpis or payload.summary_metrics or {}),
            )
        except ReportStorageConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ReportStorageError as exc:
            raise HTTPException(status_code=502, detail="Failed to store saved report payload") from exc

        saved_version_name = str(getattr(saved, "version_name", "") or "").strip() or None
        if saved_version_name is None and isinstance(saved.results_json, dict):
            saved_version_name = str(saved.results_json.get("version_name") or "").strip() or None
        return SavedResultsVersionItem(
            id=saved.id,
            created_at=saved.created_at.isoformat(),
            updated_at=saved.updated_at.isoformat(),
            version_name=saved_version_name,
        )


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
    try:
        tagged_cells = exception_tagging_service.build_tagged_cells(
            exception_id=payload.exception_id,
            addresses=payload.addresses,
            tagged_cells=payload.tagged_cells,
            sheet_name=payload.sheet_name,
            workbook_name=payload.workbook_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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


async def get_result_version_payload(
    version_id: int,
    subscription: Subscription = Depends(get_authenticated_subscription),
) -> SavedResultsVersionPayloadResponse:
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    user_id, organisation_id = _require_db_backed_user(subscription)

    async with async_session_maker() as session:
        try:
            payload = await get_results_version_payload_by_id(
                session,
                organisation_id=organisation_id,
                user_id=user_id,
                version_id=version_id,
            )
        except ReportObjectNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReportPayloadFormatError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ReportStorageConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ReportStorageError as exc:
            raise HTTPException(status_code=502, detail="Failed to load saved report payload") from exc

        if payload is None:
            raise HTTPException(status_code=404, detail="Saved result version not found")
        return SavedResultsVersionPayloadResponse(**payload)


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
        return results_domain_service.build_version_comparison(
            saved_versions=saved_versions,
            current_workbook=current_workbook,
            current_sheet=current_sheet,
        )


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
                worksheet_snapshot=payload.worksheet_snapshot,
                excel_file_base64=payload.excel_file_base64,
                excel_source_sheet_name=payload.excel_source_sheet_name,
                tagged_cells=payload.tagged_cells,
                version_name=payload.version_name,
                kpis=dict(payload.kpis or payload.summary_metrics or {}),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ReportStorageConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ReportStorageError as exc:
            raise HTTPException(status_code=502, detail="Failed to update saved report payload") from exc

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



