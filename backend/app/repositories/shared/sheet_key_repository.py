from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SheetKey
from app.common.utilities.normalization import (
    UNKNOWN_SHEET,
    UNKNOWN_WORKBOOK,
    normalize_pack_storage_value,
    normalize_scope_value,
)


class SheetKeyRepository:
    """Repository for sheet key lookups and creation."""

    @staticmethod
    async def find(
        session: AsyncSession,
        *,
        organisation_id: int,
        workbook_name: str | None,
        sheet_name: str | None,
        test_pack: str | None = None,
    ) -> SheetKey | None:
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
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        *,
        organisation_id: int,
        workbook_name: str | None,
        sheet_name: str | None,
        test_pack: str | None = None,
    ) -> SheetKey:
        sheet_key = await SheetKeyRepository.find(
            session,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )
        if sheet_key is not None:
            return sheet_key

        now = datetime.now(timezone.utc)
        sheet_key = SheetKey(
            organisation_id=organisation_id,
            workbook_name=normalize_scope_value(workbook_name, fallback=UNKNOWN_WORKBOOK),
            sheet_name=normalize_scope_value(sheet_name, fallback=UNKNOWN_SHEET),
            test_pack=normalize_pack_storage_value(test_pack),
            created_at=now,
            updated_at=now,
        )
        session.add(sheet_key)
        await session.flush()
        return sheet_key
