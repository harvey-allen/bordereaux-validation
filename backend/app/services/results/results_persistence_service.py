"""
Service for storing and retrieving validation test results.

Run history is stored as one ValidationRun row per validation call.
Saved snapshots (pass/fail summaries chosen by the user) continue to use
ValidationResultVersion, with worksheet payloads stored in S3 and only
location metadata stored in ValidationResultPayload.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    SheetKey,
    UserSubscription,
    ValidationResultPayload,
    ValidationResultVersion,
    ValidationRun,
)
from app.common.utilities.normalization import (
    UNKNOWN_SHEET,
    UNKNOWN_WORKBOOK,
    normalize_pack_storage_value,
    normalize_scope_value,
)
from app.repositories.results.results_repository import ResultsRepository
from app.repositories.shared.sheet_key_repository import SheetKeyRepository
from app.services.results.report_storage_service import (
    ReportObjectNotFoundError,
    ReportPayloadFormatError,
    ReportStorageError,
    report_storage_service,
)


logger = logging.getLogger(__name__)


def _column_to_a1(col_index_zero_based: int) -> str:
    dividend = int(col_index_zero_based) + 1
    column_name = ""
    while dividend > 0:
        modulo = (dividend - 1) % 26
        column_name = chr(65 + modulo) + column_name
        dividend = (dividend - modulo) // 26
    return column_name


def _excel_heatmap_hex(score: Any) -> str:
    start_red, start_green, start_blue = 255, 235, 238
    end_red, end_green, end_blue = 139, 0, 0
    scale_cap = 10

    try:
        numeric_score = int(float(score or 0))
    except Exception:
        numeric_score = 0

    if numeric_score <= 0:
        return "FFFFFF"

    level = max(1, min(scale_cap, numeric_score))
    ratio = (level - 1) / (scale_cap - 1)
    red = round(start_red + (end_red - start_red) * ratio)
    green = round(start_green + (end_green - start_green) * ratio)
    blue = round(start_blue + (end_blue - start_blue) * ratio)
    return f"{red:02X}{green:02X}{blue:02X}"


def _safe_sheet_title(raw_name: str | None) -> str:
    value = str(raw_name or "").strip() or "Saved Report"
    value = re.sub(r"[\\/*\[\]:?]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:31] or "Saved Report"


def _address_from_result_item(item: dict[str, Any]) -> str | None:
    raw_address = str(item.get("address") or "").strip()
    if raw_address:
        cell_address = raw_address.split("!")[-1].replace("$", "").strip().upper()
        if cell_address:
            return cell_address

    try:
        row_index = int(item.get("rowIndex"))
        col_index = int(item.get("columnIndex"))
    except Exception:
        return None

    if row_index < 0 or col_index < 0:
        return None
    return f"{_column_to_a1(col_index)}{row_index + 1}"


def _build_workbook_bytes_from_snapshot(snapshot: dict[str, Any]) -> bytes:
    mapped_headers = snapshot.get("mapped_headers") if isinstance(snapshot.get("mapped_headers"), dict) else {}
    saved_data = snapshot.get("saved_data") if isinstance(snapshot.get("saved_data"), list) else []
    validation_results = (
        snapshot.get("validation_results") if isinstance(snapshot.get("validation_results"), list) else []
    )
    tagged_cells = snapshot.get("tagged_cells") if isinstance(snapshot.get("tagged_cells"), list) else []

    headers: list[str] = []
    header_set: set[str] = set()

    for row in saved_data:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            normalized_key = str(key or "").strip()
            if normalized_key and normalized_key not in header_set:
                header_set.add(normalized_key)
                headers.append(normalized_key)

    if not headers:
        for source_key, mapped_value in mapped_headers.items():
            value = str(mapped_value or "").strip() or str(source_key or "").strip()
            if value and value not in header_set:
                header_set.add(value)
                headers.append(value)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = _safe_sheet_title(snapshot.get("source_sheet_name") or snapshot.get("sheet_name"))

    if headers:
        for col_idx, header in enumerate(headers, start=1):
            cell = worksheet.cell(row=1, column=col_idx, value=header)
            cell.font = Font(bold=True)

    for row_idx, row in enumerate(saved_data, start=2):
        row_dict = row if isinstance(row, dict) else {}
        for col_idx, header in enumerate(headers, start=1):
            worksheet.cell(row=row_idx, column=col_idx, value=row_dict.get(header))

    for item in validation_results:
        if not isinstance(item, dict):
            continue
        address = _address_from_result_item(item)
        if not address:
            continue
        cell = worksheet[address]

        severity_score = item.get("severityScore")
        if severity_score is None:
            severity_score = item.get("failCount")
        fill_hex = _excel_heatmap_hex(severity_score)
        cell.fill = PatternFill(fill_type="solid", fgColor=fill_hex)

        try:
            fail_count = int(item.get("failCount") or 0)
            row_index = int(item.get("rowIndex") or 0)
        except Exception:
            fail_count, row_index = 0, 0

        if fail_count > 0 and row_index > 0:
            comment_text = str(item.get("comment") or "Validation failure").strip() or "Validation failure"
            if len(comment_text) > 4000:
                comment_text = f"{comment_text[:3999]}…"
            cell.comment = Comment(text=comment_text, author="Bordereaux Validator")

    for tagged in tagged_cells:
        if not isinstance(tagged, dict):
            continue
        address = str(tagged.get("address") or "").replace("$", "").strip().upper()
        if not address:
            continue
        cell = worksheet[address]
        fill_color = str(tagged.get("fill_color") or tagged.get("fillColor") or "#dbeafe").strip()
        fill_hex = fill_color.lstrip("#")
        if len(fill_hex) == 6:
            cell.fill = PatternFill(fill_type="solid", fgColor=fill_hex.upper())
        comment_text = str(tagged.get("comment") or "").strip()
        if comment_text:
            cell.comment = Comment(text=comment_text[:4000], author="Bordereaux Validator")

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def _get_or_create_sheet_key(
    session: AsyncSession,
    *,
    organisation_id: int,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str | None = None,
):
    return await SheetKeyRepository.get_or_create(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=test_pack,
    )


async def _find_sheet_key(
    session: AsyncSession,
    *,
    organisation_id: int,
    workbook_name: str | None,
    sheet_name: str | None,
    test_pack: str | None = None,
):
    """Return an existing sheet key if present, without creating one."""
    return await SheetKeyRepository.find(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=test_pack,
    )


async def _get_organisation_storage_prefix(
    session: AsyncSession,
    *,
    organisation_id: int,
) -> str:
    """Return organisation storage prefix for report S3 keys."""
    organisation_name = await ResultsRepository.get_organisation_name_by_id(
        session,
        organisation_id=organisation_id,
    )
    normalized_name = str(organisation_name or "").strip()
    if normalized_name:
        return normalized_name
    return str(int(organisation_id))


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
    tagged_cells_json: list[dict[str, Any]] = field(default_factory=list)
    user_id: int | None = None
    api_key_hash: str | None = None


@dataclass
class SavedVersionWithScope:
    """Saved result version enriched with workbook/sheet scope metadata."""

    version: ValidationResultVersion
    workbook_name: str
    sheet_name: str


def _normalize_tagged_cells(tagged_cells: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize tagged cell payloads for stable JSON persistence."""
    normalized: list[dict[str, Any]] = []
    for item in tagged_cells or []:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or "").strip().upper()
        exception_id = str(item.get("exception_id") or item.get("exceptionId") or "").strip()
        if not address or not exception_id:
            continue
        normalized.append(
            {
                "address": address,
                "exception_id": exception_id,
                "comment": str(item.get("comment") or f"Exception tagged: {exception_id}").strip(),
                "fill_color": str(item.get("fill_color") or item.get("fillColor") or "#dbeafe").strip() or "#dbeafe",
                "previous_fill_color": str(item.get("previous_fill_color") or item.get("previousFillColor") or "").strip(),
                "sheet_name": normalize_scope_value(item.get("sheet_name") or item.get("sheetName"), fallback=UNKNOWN_SHEET),
                "workbook_name": normalize_scope_value(item.get("workbook_name") or item.get("workbookName"), fallback=UNKNOWN_WORKBOOK),
                "tagged_at": str(item.get("tagged_at") or item.get("taggedAt") or datetime.now(timezone.utc).isoformat()).strip(),
            }
        )
    return normalized


def _merge_tagged_cells(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge tagged cells by workbook+sheet+address, preferring incoming values."""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in _normalize_tagged_cells(existing):
        key = (item["workbook_name"], item["sheet_name"], item["address"])
        merged[key] = item
    for item in _normalize_tagged_cells(incoming):
        key = (item["workbook_name"], item["sheet_name"], item["address"])
        merged[key] = item
    return list(merged.values())


def _is_matching_exception_tag(item: Any, exception_id: str) -> bool:
    """Return True when the tagged-cell record references the provided exception id."""
    if not isinstance(item, dict):
        return False
    tag_exception_id = str(item.get("exception_id") or item.get("exceptionId") or "").strip()
    return bool(tag_exception_id) and tag_exception_id == exception_id


async def remove_exception_tags_from_results(
    session: AsyncSession,
    *,
    organisation_id: int,
    exception_id: str,
) -> dict[str, Any]:
    """Remove all tagged-cell references to an exception from persisted runs and saved result versions."""
    normalized_exception_id = str(exception_id or "").strip()
    if not normalized_exception_id:
        return {
            "runs_updated": 0,
            "versions_updated": 0,
            "tags_removed": 0,
            "removed_tagged_cells": [],
        }

    runs_updated = 0
    versions_updated = 0
    tags_removed = 0
    removed_tagged_cells: list[dict[str, Any]] = []

    run_result = await session.execute(
        select(ValidationRun)
        .join(SheetKey, ValidationRun.sheet_key_id == SheetKey.id)
        .where(SheetKey.organisation_id == organisation_id)
    )
    for run in run_result.scalars().all():
        current_tags = list(run.tagged_cells_json or [])
        kept_tags: list[dict[str, Any]] = []
        run_changed = False
        for tag in current_tags:
            if _is_matching_exception_tag(tag, normalized_exception_id):
                run_changed = True
                tags_removed += 1
                normalized_tag = _normalize_tagged_cells([tag])
                if normalized_tag:
                    removed_tagged_cells.append(normalized_tag[0])
                continue
            kept_tags.append(tag)

        if run_changed:
            run.tagged_cells_json = kept_tags
            runs_updated += 1

    version_result = await session.execute(
        select(ValidationResultVersion)
        .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
        .where(SheetKey.organisation_id == organisation_id)
    )
    for version in version_result.scalars().all():
        current_tags = list(version.tagged_cells_json or [])
        kept_tags: list[dict[str, Any]] = []
        version_changed = False
        for tag in current_tags:
            if _is_matching_exception_tag(tag, normalized_exception_id):
                version_changed = True
                continue
            kept_tags.append(tag)

        if version_changed:
            version.tagged_cells_json = kept_tags
            versions_updated += 1

    deduped_removed_tags: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for tag in removed_tagged_cells:
        workbook_name = str(tag.get("workbook_name") or "").strip()
        sheet_name = str(tag.get("sheet_name") or "").strip()
        address = str(tag.get("address") or "").strip().upper()
        tag_exception_id = str(tag.get("exception_id") or "").strip()
        if not workbook_name or not sheet_name or not address or not tag_exception_id:
            continue
        deduped_removed_tags[(workbook_name, sheet_name, address, tag_exception_id)] = tag

    return {
        "runs_updated": runs_updated,
        "versions_updated": versions_updated,
        "tags_removed": tags_removed,
        "removed_tagged_cells": list(deduped_removed_tags.values()),
    }


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
    worksheet_snapshot: dict[str, Any] | None = None,
    excel_file_base64: str | None = None,
    excel_source_sheet_name: str | None = None,
    tagged_cells: list[dict[str, Any]] | None = None,
    version_name: str | None = None,
    kpis: dict[str, Any] | None = None,
) -> ValidationResultVersion:
    """
    Upsert one saved result per (sheet_key, test_pack).

    Pass/fail UMR lists are written to ValidationResultVersion.results_json.
    mapped_headers and saved_data are written to S3 via the companion
    ValidationResultPayload row location metadata (one-to-one).
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
        "KPIs": dict(kpis or {}),
        "summary_metrics": dict(kpis or {}),
    }

    # Upsert ValidationResultVersion
    version = await ResultsRepository.get_version_for_sheet_key_pack(
        session,
        sheet_key_id=int(sheet_key.id),
        test_pack=normalized_test_pack,
    )
    now = datetime.now(timezone.utc)

    incoming_version_name = str(version_name or "").strip() or None
    existing_version_name = str(getattr(version, "version_name", "") or "").strip() or None if version is not None else None
    if existing_version_name is None and version is not None and isinstance(version.results_json, dict):
        existing_version_name = str(version.results_json.get("version_name") or "").strip() or None
    effective_version_name = incoming_version_name or existing_version_name

    if version is None:
        if effective_version_name:
            results_json["version_name"] = effective_version_name
        version = ValidationResultVersion(
            sheet_key_id=int(sheet_key.id),
            user_id=user_id,
            test_pack=normalized_test_pack,
            version_name=effective_version_name,
            results_json=results_json,
            tagged_cells_json=_normalize_tagged_cells(tagged_cells),
            created_at=now,
            updated_at=now,
        )
        session.add(version)
        await session.flush()
    else:
        if effective_version_name:
            results_json["version_name"] = effective_version_name
        version.results_json = results_json
        version.tagged_cells_json = _normalize_tagged_cells(tagged_cells)
        version.user_id = user_id
        version.test_pack = normalized_test_pack
        version.version_name = effective_version_name
        version.updated_at = now
        await session.flush()

    worksheet_payload: dict[str, Any] = {
        "mapped_headers": dict(mapped_headers or {}),
        "saved_data": list(saved_data or []),
    }
    if isinstance(worksheet_snapshot, dict):
        worksheet_payload["worksheet_snapshot"] = dict(worksheet_snapshot)
    excel_payload_base64 = str(excel_file_base64 or "").strip() or None

    payload = await ResultsRepository.get_payload_for_version(
        session,
        version_id=int(version.id),
    )

    try:
        if payload is None:
            payload = ValidationResultPayload(
                validation_result_version_id=int(version.id),
                version_name=effective_version_name,
                s3_location="__pending__",
                created_at=now,
                updated_at=now,
            )
            session.add(payload)
            await session.flush()

        if not str(payload.s3_location or "").strip() or payload.s3_location == "__pending__":
            organisation_storage_prefix = await _get_organisation_storage_prefix(
                session,
                organisation_id=organisation_id,
            )
            file_extension = "xlsx" if excel_payload_base64 or isinstance(worksheet_snapshot, dict) else "json"
            payload.s3_location = report_storage_service.generate_s3_key(
                organisation_name=organisation_storage_prefix,
                report_id=int(payload.id),
                file_extension=file_extension,
            )

        if excel_payload_base64:
            try:
                excel_payload_bytes = base64.b64decode(excel_payload_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ReportPayloadFormatError("Invalid Excel payload: expected base64-encoded workbook") from exc

            if not excel_payload_bytes:
                raise ReportPayloadFormatError("Invalid Excel payload: workbook is empty")

            await report_storage_service.upload_report_bytes(
                s3_key=payload.s3_location,
                body=excel_payload_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif isinstance(worksheet_snapshot, dict):
            workbook_bytes = _build_workbook_bytes_from_snapshot(worksheet_snapshot)
            await report_storage_service.upload_report_bytes(
                s3_key=payload.s3_location,
                body=workbook_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            await report_storage_service.upload_report(
                s3_key=payload.s3_location,
                payload=worksheet_payload,
            )

        payload.version_name = effective_version_name
        payload.updated_at = now
        await session.commit()
    except ReportStorageError:
        await session.rollback()
        raise

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
    sheet_key = await _find_sheet_key(
        session,
        organisation_id=organisation_id,
        workbook_name=workbook_name,
        sheet_name=sheet_name,
        test_pack=normalized_test_pack,
    )
    if sheet_key is None:
        return None
    return await ResultsRepository.get_version_for_sheet_key_pack(
        session,
        sheet_key_id=int(sheet_key.id),
        test_pack=normalized_test_pack,
    )


async def list_results_versions_for_pack(
    session: AsyncSession,
    *,
    organisation_id: int,
    test_pack: str,
) -> list[SavedVersionWithScope]:
    """Return all saved result versions for an organisation and test pack, newest first."""
    normalized_test_pack = normalize_pack_storage_value(test_pack)
    rows = await ResultsRepository.list_versions_for_org_pack(
        session,
        organisation_id=organisation_id,
        test_pack=normalized_test_pack,
    )

    items: list[SavedVersionWithScope] = []
    for version, sheet_key in rows:
        items.append(
            SavedVersionWithScope(
                version=version,
                workbook_name=sheet_key.workbook_name,
                sheet_name=sheet_key.sheet_name,
            )
        )
    return items


async def delete_results_version(
    session: AsyncSession,
    *,
    organisation_id: int,
    sheet_key_id: int,
) -> bool:
    """Delete result versions for a sheet_key, constrained to org ownership."""
    version = await ResultsRepository.get_version_by_sheet_key_for_org(
        session,
        organisation_id=organisation_id,
        sheet_key_id=sheet_key_id,
    )
    if version is None:
        return False

    payload = await ResultsRepository.get_payload_for_version(
        session,
        version_id=int(version.id),
    )
    if payload is not None and str(payload.s3_location or "").strip():
        try:
            await report_storage_service.delete_report(s3_key=str(payload.s3_location))
        except ReportObjectNotFoundError:
            logger.warning(
                "S3 report object already missing during delete",
                extra={
                    "organisation_id": organisation_id,
                    "version_id": int(version.id),
                    "s3_location": payload.s3_location,
                },
            )
        except ReportStorageError:
            logger.exception(
                "Failed deleting S3 report object",
                extra={
                    "organisation_id": organisation_id,
                    "version_id": int(version.id),
                    "s3_location": payload.s3_location,
                },
            )

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
    version_with_scope = await ResultsRepository.get_version_by_id_for_org(
        session,
        organisation_id=organisation_id,
        version_id=version_id,
    )
    version = version_with_scope[0] if version_with_scope is not None else None
    if version is None:
        return False

    payload = await ResultsRepository.get_payload_for_version(
        session,
        version_id=int(version.id),
    )
    if payload is not None and str(payload.s3_location or "").strip():
        try:
            await report_storage_service.delete_report(s3_key=str(payload.s3_location))
        except ReportObjectNotFoundError:
            logger.warning(
                "S3 report object already missing during delete by id",
                extra={
                    "organisation_id": organisation_id,
                    "version_id": int(version.id),
                    "s3_location": payload.s3_location,
                },
            )
        except ReportStorageError:
            logger.exception(
                "Failed deleting S3 report object during delete by id",
                extra={
                    "organisation_id": organisation_id,
                    "version_id": int(version.id),
                    "s3_location": payload.s3_location,
                },
            )

    await session.delete(version)
    await session.commit()
    return True


async def update_results_version_by_id(
    session: AsyncSession,
    *,
    organisation_id: int,
    user_id: int | None,
    version_id: int,
    test_pack: str,
    failed_tests: list[dict[str, str]],
    passed_tests: list[str],
    passed_umrs: list[str] | None = None,
    mapped_headers: dict[str, str] | None = None,
    saved_data: list[dict[str, Any]] | None = None,
    worksheet_snapshot: dict[str, Any] | None = None,
    excel_file_base64: str | None = None,
    excel_source_sheet_name: str | None = None,
    tagged_cells: list[dict[str, Any]] | None = None,
    version_name: str | None = None,
    kpis: dict[str, Any] | None = None,
) -> ValidationResultVersion | None:
    """Update an existing saved result version by id within the same sheet_key context."""
    normalized_test_pack = normalize_pack_storage_value(test_pack)

    version_with_scope = await ResultsRepository.get_version_by_id_for_org(
        session,
        organisation_id=organisation_id,
        version_id=version_id,
    )
    if version_with_scope is None:
        return None

    version, _sheet_key = version_with_scope
    existing_pack = normalize_pack_storage_value(version.test_pack)
    if existing_pack != normalized_test_pack:
        raise ValueError("test_pack does not match the selected saved version")

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
        "passed_ids": passed_test_list,
        "test_pack": existing_pack,
        "KPIs": dict(kpis or {}),
        "summary_metrics": dict(kpis or {}),
    }

    now = datetime.now(timezone.utc)
    incoming_version_name = str(version_name or "").strip() or None
    existing_version_name = str(getattr(version, "version_name", "") or "").strip() or None
    if existing_version_name is None and isinstance(version.results_json, dict):
        existing_version_name = str(version.results_json.get("version_name") or "").strip() or None
    effective_version_name = incoming_version_name or existing_version_name

    if effective_version_name:
        results_json["version_name"] = effective_version_name

    version.results_json = results_json
    version.tagged_cells_json = _normalize_tagged_cells(tagged_cells)
    version.user_id = user_id
    version.test_pack = existing_pack
    version.version_name = effective_version_name
    version.updated_at = now
    await session.flush()

    worksheet_payload: dict[str, Any] = {
        "mapped_headers": dict(mapped_headers or {}),
        "saved_data": list(saved_data or []),
    }
    if isinstance(worksheet_snapshot, dict):
        worksheet_payload["worksheet_snapshot"] = dict(worksheet_snapshot)
    excel_payload_base64 = str(excel_file_base64 or "").strip() or None

    payload = await ResultsRepository.get_payload_for_version(
        session,
        version_id=int(version.id),
    )

    try:
        if payload is None:
            payload = ValidationResultPayload(
                validation_result_version_id=int(version.id),
                version_name=effective_version_name,
                s3_location="__pending__",
                created_at=now,
                updated_at=now,
            )
            session.add(payload)
            await session.flush()

        if not str(payload.s3_location or "").strip() or payload.s3_location == "__pending__":
            organisation_storage_prefix = await _get_organisation_storage_prefix(
                session,
                organisation_id=organisation_id,
            )
            file_extension = "xlsx" if excel_payload_base64 or isinstance(worksheet_snapshot, dict) else "json"
            payload.s3_location = report_storage_service.generate_s3_key(
                organisation_name=organisation_storage_prefix,
                report_id=int(payload.id),
                file_extension=file_extension,
            )

        if excel_payload_base64:
            try:
                excel_payload_bytes = base64.b64decode(excel_payload_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ReportPayloadFormatError("Invalid Excel payload: expected base64-encoded workbook") from exc

            if not excel_payload_bytes:
                raise ReportPayloadFormatError("Invalid Excel payload: workbook is empty")

            await report_storage_service.upload_report_bytes(
                s3_key=payload.s3_location,
                body=excel_payload_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        elif isinstance(worksheet_snapshot, dict):
            workbook_bytes = _build_workbook_bytes_from_snapshot(worksheet_snapshot)
            await report_storage_service.upload_report_bytes(
                s3_key=payload.s3_location,
                body=workbook_bytes,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            await report_storage_service.upload_report(
                s3_key=payload.s3_location,
                payload=worksheet_payload,
            )

        payload.version_name = effective_version_name
        payload.updated_at = now
        await session.commit()
    except ReportStorageError:
        await session.rollback()
        raise

    await session.refresh(version)
    return version


async def get_results_version_payload_by_id(
    session: AsyncSession,
    *,
    organisation_id: int,
    user_id: int,
    version_id: int,
) -> dict[str, Any] | None:
    """Return saved version payload + scope + pack config for a specific version id."""
    version_with_scope = await ResultsRepository.get_version_by_id_for_org(
        session,
        organisation_id=organisation_id,
        version_id=version_id,
    )
    if version_with_scope is None:
        return None

    version, sheet_key = version_with_scope

    payload = await ResultsRepository.get_payload_for_version(
        session,
        version_id=int(version.id),
    )

    pack_config = None
    version_owner_user_id = int(version.user_id) if getattr(version, "user_id", None) is not None else None

    if version_owner_user_id is not None:
        pack_config = await ResultsRepository.get_pack_config_for_user_sheet_pack(
            session,
            user_id=version_owner_user_id,
            sheet_key_id=int(sheet_key.id),
            test_pack=version.test_pack,
        )

    if pack_config is None and (version_owner_user_id is None or version_owner_user_id != user_id):
        pack_config = await ResultsRepository.get_pack_config_for_user_sheet_pack(
            session,
            user_id=user_id,
            sheet_key_id=int(sheet_key.id),
            test_pack=version.test_pack,
        )

    if pack_config is None:
        pack_config = await ResultsRepository.get_latest_pack_config_for_sheet_pack(
            session,
            sheet_key_id=int(sheet_key.id),
            test_pack=version.test_pack,
        )

    version_name = str(getattr(version, "version_name", "") or "").strip() or None
    if version_name is None and isinstance(version.results_json, dict):
        version_name = str(version.results_json.get("version_name") or "").strip() or None
    if version_name is None and payload is not None:
        version_name = str(getattr(payload, "version_name", "") or "").strip() or None

    if payload is None:
        raise ReportObjectNotFoundError(f"Saved report payload not found for version id {version_id}")

    s3_location = str(payload.s3_location or "").strip()
    if not s3_location:
        raise ReportObjectNotFoundError(f"Saved report payload location missing for version id {version_id}")

    mapped_headers: dict[str, Any] = {}
    saved_data: list[Any] = []
    worksheet_snapshot: dict[str, Any] | None = None
    excel_file_base64: str | None = None

    if s3_location.lower().endswith(".xlsx"):
        workbook_bytes = await report_storage_service.download_report_bytes(s3_key=s3_location)
        if not workbook_bytes:
            raise ReportPayloadFormatError(f"Saved workbook payload is empty for version id {version_id}")
        excel_file_base64 = base64.b64encode(workbook_bytes).decode("ascii")
    else:
        worksheet_payload = await report_storage_service.download_report(s3_key=s3_location)
        mapped_headers = worksheet_payload.get("mapped_headers", {})
        saved_data = worksheet_payload.get("saved_data", [])
        snapshot_value = worksheet_payload.get("worksheet_snapshot")
        if snapshot_value is not None:
            if not isinstance(snapshot_value, dict):
                raise ReportPayloadFormatError(
                    f"Invalid worksheet_snapshot payload type for version id {version_id}: expected object"
                )
            worksheet_snapshot = dict(snapshot_value)
        if not isinstance(mapped_headers, dict):
            raise ReportPayloadFormatError(
                f"Invalid mapped_headers payload type for version id {version_id}: expected object"
            )
        if not isinstance(saved_data, list):
            raise ReportPayloadFormatError(
                f"Invalid saved_data payload type for version id {version_id}: expected array"
            )

    return {
        "id": int(version.id),
        "sheet_key_id": int(sheet_key.id),
        "test_pack": str(version.test_pack or "").strip(),
        "version_name": version_name,
        "workbook_name": str(sheet_key.workbook_name or "").strip(),
        "sheet_name": str(sheet_key.sheet_name or "").strip(),
        "created_at": version.created_at.isoformat(),
        "updated_at": version.updated_at.isoformat(),
        "mapped_headers": mapped_headers,
        "saved_data": saved_data,
        "worksheet_snapshot": worksheet_snapshot,
        "excel_file_base64": excel_file_base64,
        "excel_source_sheet_name": str(sheet_key.sheet_name or "").strip(),
        "tagged_cells": list(version.tagged_cells_json or []),
        "pack_config": dict(pack_config.config_json or {}) if pack_config is not None else {},
    }


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
        tagged_cells_json=list(row.tagged_cells_json or []),
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
    tagged_cells: list[dict[str, Any]] | None = None,
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
    existing_tagged_cells: list[dict[str, Any]] = []

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
        prior_row = await ResultsRepository.get_latest_run_for_scope(
            session,
            sheet_name=sheet_name,
            workbook_name=workbook_name,
            user_id=user_id,
            api_key_hash=api_key_hash,
        )
        if prior_row is not None:
            existing_tagged_cells = list(prior_row.tagged_cells_json or [])

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
        tagged_cells_json=_merge_tagged_cells(existing_tagged_cells, tagged_cells),
    )
    session.add(run)
    await session.commit()

    return _run_to_summary(run)


async def upsert_validation_run_tagged_cells(
    session: AsyncSession,
    *,
    organisation_id: int,
    user_id: int,
    workbook_name: str | None,
    sheet_name: str,
    test_pack: str | None,
    tagged_cells: list[dict[str, Any]],
) -> RunSummary:
    """Update the latest validation run for a sheet with tagged-cell JSON, creating one if missing."""
    normalized_workbook = normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK)
    normalized_sheet = normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET)
    normalized_pack = normalize_pack_storage_value(test_pack)

    result = await session.execute(
        select(ValidationRun)
        .where(ValidationRun.user_id == user_id)
        .where(ValidationRun.workbook_name == normalized_workbook)
        .where(ValidationRun.sheet_name == normalized_sheet)
        .order_by(desc(ValidationRun.run_timestamp))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    normalized_tags = _normalize_tagged_cells(tagged_cells)

    if run is None:
        sheet_key = await _get_or_create_sheet_key(
            session,
            organisation_id=organisation_id,
            workbook_name=normalized_workbook,
            sheet_name=normalized_sheet,
            test_pack=normalized_pack,
        )
        run_token = int(now.timestamp() * 1_000_000)
        run = ValidationRun(
            run_token=run_token,
            run_timestamp=now,
            sheet_key_id=int(sheet_key.id),
            user_id=user_id,
            api_key_hash=None,
            workbook_name=normalized_workbook,
            sheet_name=normalized_sheet,
            range_address=None,
            test_packs=normalized_pack,
            total_rows=0,
            total_cells=0,
            failed_cells=0,
            passed_cells=0,
            status="tagged",
            error_message=None,
            coverage_json={},
            tagged_cells_json=normalized_tags,
        )
        session.add(run)
    else:
        run.tagged_cells_json = _merge_tagged_cells(run.tagged_cells_json, normalized_tags)
        if not run.test_packs.strip() and normalized_pack:
            run.test_packs = normalized_pack

    await session.commit()
    await session.refresh(run)
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
    row = await ResultsRepository.get_run_by_token(
        session,
        run_token=run_token,
    )
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
