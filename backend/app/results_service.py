"""
Service for storing and retrieving validation test results.

Run history is stored as one ValidationRun row per validation call.
Saved snapshots (pass/fail summaries chosen by the user) continue to use
ValidationResultVersion, with mapped_headers + saved_data in the companion
ValidationResultPayload table.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    SheetKey,
    UserSubscription,
    ValidationResultPayload,
    ValidationResultVersion,
    ValidationRun,
)
from app.utils.normalization import (
    UNKNOWN_SHEET,
    UNKNOWN_WORKBOOK,
    normalize_pack_storage_value,
    normalize_scope_value,
)


async def _get_or_create_sheet_key(
    session: AsyncSession,
    *,
    organisation_id: int,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str | None = None,
) -> SheetKey:
    normalized_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
    normalized_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)
    normalized_pack = normalize_pack_storage_value(test_pack)

    result = await session.execute(
        select(SheetKey)
        .where(SheetKey.organisation_id == organisation_id)
        .where(SheetKey.workbook_name == normalized_workbook)
        .where(SheetKey.sheet_name == normalized_sheet)
        .where(SheetKey.test_pack == normalized_pack)
    )
    sheet_key = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if sheet_key is not None:
        return sheet_key

    sheet_key = SheetKey(
        organisation_id=organisation_id,
        workbook_name=normalized_workbook,
        sheet_name=normalized_sheet,
        test_pack=normalized_pack,
        created_at=now,
        updated_at=now,
    )
    session.add(sheet_key)
    await session.flush()
    return sheet_key


# ---------------------------------------------------------------------------
# RunSummary dataclass — presents the same attribute interface that main.py
# previously consumed from the ValidationRun ORM model.
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    """Lightweight run view built from a single ValidationRun row."""

    id: int                    # == run_token (unix microseconds)
    timestamp: datetime
    workbook_name: str | None
    sheet_name: str | None
    range_address: str | None
    total_rows: int
    total_cells: int
    failed_cells: int
    passed_cells: int
    status: str
    error_message: str | None
    test_packs: str            # comma-separated
    coverage_json: dict = field(default_factory=dict)
    user_id: int | None = None
    api_key_hash: str | None = None


async def get_or_create_sheet_key(
    session: AsyncSession,
    *,
    organisation_id: int,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str | None = None,
) -> SheetKey:
    """Public wrapper for callers that need a consistent sheet key lookup."""
    return await _get_or_create_sheet_key(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=test_pack,
    )


# ---------------------------------------------------------------------------
# Saved result versions
# ---------------------------------------------------------------------------

async def save_results_version(
    session: AsyncSession,
    *,
    organisation_id: int,
    user_id: int | None,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str,
    failed_tests: list[dict[str, str]],
    passed_tests: list[str],
    passed_umrs: list[str] | None = None,
    mapped_headers: dict[str, str] | None = None,
    saved_data: list[dict[str, Any]] | None = None,
) -> ValidationResultVersion:
    """
    Upsert one saved result per (sheet_key, test_pack).

    Pass/fail UMR lists are written to ValidationResultVersion.results_json.
    mapped_headers and saved_data are written to a companion
    ValidationResultPayload row (one-to-one with the version row).
    """
    normalized_test_pack = normalize_pack_storage_value(test_pack)

    sheet_key = await _get_or_create_sheet_key(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=normalized_test_pack,
    )

    # Build failed-UMR map: {umr -> [test_ids]}
    failed_by_umr: dict[str, list[str]] = {}
    for item in (failed_tests or []):
        umr = str(item.get("umr") or item.get("id") or "")
        test_id = str(item.get("test_id", ""))
        if umr and test_id:
            failed_by_umr.setdefault(umr, []).append(test_id)

    passed_test_list = [str(t) for t in (passed_tests or []) if str(t or "").strip()]
    passed_umr_list = [str(u) for u in (passed_umrs or []) if str(u or "").strip()]

    results_json: dict[str, Any] = {
        "failed": [{"id": umr, "tests": tests} for umr, tests in failed_by_umr.items()],
        "passed_umrs": passed_umr_list,
        "passed_tests": passed_test_list,
        "passed_ids": passed_test_list,  # legacy compatibility
        "test_pack": normalized_test_pack,
    }

    # Upsert ValidationResultVersion
    ver_result = await session.execute(
        select(ValidationResultVersion)
        .where(ValidationResultVersion.sheet_key_id == int(sheet_key.id))
        .where(ValidationResultVersion.test_pack == normalized_test_pack)
    )
    version = ver_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if version is None:
        version = ValidationResultVersion(
            sheet_key_id=int(sheet_key.id),
            user_id=user_id,
            test_pack=normalized_test_pack,
            results_json=results_json,
            created_at=now,
            updated_at=now,
        )
        session.add(version)
        await session.flush()
    else:
        version.results_json = results_json
        version.user_id = user_id
        version.test_pack = normalized_test_pack
        version.updated_at = now
        await session.flush()

    # Upsert ValidationResultPayload (mapped_headers + saved_data)
    pay_result = await session.execute(
        select(ValidationResultPayload)
        .where(ValidationResultPayload.validation_result_version_id == int(version.id))
    )
    payload = pay_result.scalar_one_or_none()

    if payload is None:
        session.add(
            ValidationResultPayload(
                validation_result_version_id=int(version.id),
                mapped_headers_json=dict(mapped_headers or {}),
                saved_data_json=list(saved_data or []),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        payload.mapped_headers_json = dict(mapped_headers or {})
        payload.saved_data_json = list(saved_data or [])
        payload.updated_at = now

    await session.commit()
    await session.refresh(version)
    return version


# ---------------------------------------------------------------------------
# Get / delete saved result versions
# ---------------------------------------------------------------------------

async def get_results_version(
    session: AsyncSession,
    *,
    organisation_id: int,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str,
) -> ValidationResultVersion | None:
    """Return the saved result version for a sheet+pack, or None."""
    normalized_test_pack = normalize_pack_storage_value(test_pack)
    sheet_key = await _get_or_create_sheet_key(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=normalized_test_pack,
    )
    result = await session.execute(
        select(ValidationResultVersion)
        .where(ValidationResultVersion.sheet_key_id == int(sheet_key.id))
        .where(ValidationResultVersion.test_pack == normalized_test_pack)
    )
    return result.scalar_one_or_none()


async def delete_results_version(
    session: AsyncSession,
    *,
    organisation_id: int,
    sheet_key_id: int,
) -> bool:
    """Delete result versions for a sheet_key, constrained to org ownership."""
    result = await session.execute(
        select(ValidationResultVersion)
        .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
        .where(ValidationResultVersion.sheet_key_id == sheet_key_id)
        .where(SheetKey.organisation_id == organisation_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return False
    await session.delete(version)
    await session.commit()
    return True


async def delete_results_version_by_id(
    session: AsyncSession,
    *,
    organisation_id: int,
    version_id: int,
) -> bool:
    """Delete a specific result version by id, constrained to org ownership."""
    result = await session.execute(
        select(ValidationResultVersion)
        .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
        .where(ValidationResultVersion.id == version_id)
        .where(SheetKey.organisation_id == organisation_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return False
    await session.delete(version)
    await session.commit()
    return True


def _run_to_summary(row: ValidationRun) -> RunSummary:
    """Build a RunSummary from a single ValidationRun row."""
    return RunSummary(
        id=row.run_token,
        timestamp=row.run_timestamp,
        workbook_name=row.workbook_name,
        sheet_name=row.sheet_name,
        range_address=row.range_address,
        total_rows=row.total_rows,
        total_cells=row.total_cells,
        failed_cells=row.failed_cells,
        passed_cells=row.passed_cells,
        status=row.status,
        error_message=row.error_message,
        test_packs=row.test_packs,
        coverage_json=dict(row.coverage_json or {}),
        user_id=row.user_id,
        api_key_hash=row.api_key_hash,
    )


# ---------------------------------------------------------------------------
# Store live validation run
# ---------------------------------------------------------------------------

async def store_validation_results(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    test_packs: list[str],
    coverage_data: dict[str, Any],
    workbook_name: str | None = None,
    sheet_name: str | None = None,
    range_address: str | None = None,
    total_rows: int = 0,
    total_cells: int = 0,
    failed_cells: int = 0,
    passed_cells: int = 0,
    status: str = "completed",
    error_message: str | None = None,
) -> RunSummary:
    """
    Persist one ValidationRun row per validation call.

    Latest-only retention: any prior ValidationRun in the same
    user/workbook/sheet scope is deleted before inserting the new row.
    """
    # ------------------------------------------------------------------
    # 1. Resolve user, api_key_hash, organisation_id
    # ------------------------------------------------------------------
    api_key_hash: str | None = None
    user_id: int | None = None
    organisation_id: int = 1  # default fallback

    if owner_email:
        normalized_email = owner_email.strip().lower()
        if normalized_email:
            result = await session.execute(
                select(UserSubscription).where(
                    func.lower(UserSubscription.email) == normalized_email
                )
            )
            user = result.scalar_one_or_none()
            if user:
                user_id = user.id
                api_key_hash = user.api_key_hash
                organisation_id = user.organisation_id

    if api_key and not user_id:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await session.execute(
            select(UserSubscription).where(
                UserSubscription.api_key_hash == api_key_hash
            )
        )
        user = result.scalar_one_or_none()
        if user:
            user_id = user.id
            organisation_id = user.organisation_id

    # ------------------------------------------------------------------
    # 2. Delete prior ValidationRun rows in the same scope (latest-only)
    # ------------------------------------------------------------------
    if sheet_name:
        prior = delete(ValidationRun).where(ValidationRun.sheet_name == sheet_name)

        if user_id is not None:
            prior = prior.where(ValidationRun.user_id == user_id)
        elif api_key_hash:
            prior = prior.where(ValidationRun.api_key_hash == api_key_hash)
        else:
            prior = prior.where(ValidationRun.user_id.is_(None))
            prior = prior.where(ValidationRun.api_key_hash.is_(None))

        if workbook_name:
            prior = prior.where(ValidationRun.workbook_name == workbook_name)

        await session.execute(prior)
        await session.flush()

    # ------------------------------------------------------------------
    # 3. Resolve sheet_key using the first pack (or unknown)
    # ------------------------------------------------------------------
    first_pack = test_packs[0] if test_packs else "__unknown_pack__"
    sheet_key = await _get_or_create_sheet_key(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=first_pack,
    )

    # ------------------------------------------------------------------
    # 4. Stamp a single run identity and insert one row
    # ------------------------------------------------------------------
    run_timestamp = datetime.now(timezone.utc)
    run_token: int = int(run_timestamp.timestamp() * 1_000_000)

    run = ValidationRun(
        run_token=run_token,
        run_timestamp=run_timestamp,
        sheet_key_id=int(sheet_key.id),
        user_id=user_id,
        api_key_hash=api_key_hash,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        range_address=range_address,
        test_packs=",".join(test_packs),
        total_rows=total_rows,
        total_cells=total_cells,
        failed_cells=failed_cells,
        passed_cells=passed_cells,
        status=status,
        error_message=error_message,
        coverage_json=dict(coverage_data.get("packs", {})),
    )
    session.add(run)
    await session.commit()

    return _run_to_summary(run)


# ---------------------------------------------------------------------------
# History retrieval
# ---------------------------------------------------------------------------

async def get_validation_history(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RunSummary]:
    """Return run summaries sorted newest-first."""
    query = select(ValidationRun).order_by(desc(ValidationRun.run_timestamp))

    if owner_email:
        query = query.join(UserSubscription, ValidationRun.user_id == UserSubscription.id)
        query = query.where(
            func.lower(UserSubscription.email) == owner_email.strip().lower()
        )
    elif api_key:
        _hash = hashlib.sha256(api_key.encode()).hexdigest()
        query = query.where(ValidationRun.api_key_hash == _hash)
    elif user_id is not None:
        query = query.where(ValidationRun.user_id == user_id)

    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    return [_run_to_summary(r) for r in result.scalars().all()]


async def get_validation_run(
    session: AsyncSession,
    run_token: int,
) -> RunSummary | None:
    """Return one RunSummary for the given run_token, or None if not found."""
    result = await session.execute(
        select(ValidationRun).where(ValidationRun.run_token == run_token)
    )
    row = result.scalar_one_or_none()
    return _run_to_summary(row) if row is not None else None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

async def get_test_statistics(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    owner_email: str | None = None,
    user_id: int | None = None,
    test_pack: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Aggregate pass/fail statistics from ValidationRun.coverage_json in the period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(ValidationRun).where(ValidationRun.run_timestamp >= cutoff)

    if owner_email:
        query = query.join(UserSubscription, ValidationRun.user_id == UserSubscription.id)
        query = query.where(
            func.lower(UserSubscription.email) == owner_email.strip().lower()
        )
    elif api_key:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        query = query.where(ValidationRun.api_key_hash == api_key_hash)
    elif user_id is not None:
        query = query.where(ValidationRun.user_id == user_id)

    result = await session.execute(query)
    runs: list[ValidationRun] = list(result.scalars().all())

    total_cells = sum(r.total_cells for r in runs)
    total_failed = sum(r.failed_cells for r in runs)
    total_passed = sum(r.passed_cells for r in runs)

    test_stats: dict[str, dict[str, Any]] = {}
    for run in runs:
        for pack_name, pack_data in (run.coverage_json or {}).items():
            if test_pack and pack_name != test_pack:
                continue
            for test_name, test_data in (pack_data.get("tests") or {}).items():
                key = f"{pack_name}.{test_name}"
                if key not in test_stats:
                    test_stats[key] = {
                        "evaluated": 0,
                        "passed": 0,
                        "failed": 0,
                        "severity": test_data.get("severity"),
                    }
                test_stats[key]["evaluated"] += int(test_data.get("evaluatedRows", 0))
                test_stats[key]["passed"] += int(test_data.get("passedRows", 0))
                test_stats[key]["failed"] += int(test_data.get("failedRows", 0))

    return {
        "period_days": days,
        "total_runs": len(runs),
        "total_cells": total_cells,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "pass_rate": (total_passed / total_cells * 100) if total_cells > 0 else 0.0,
        "tests": test_stats,
    }
