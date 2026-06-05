"""Service for persisted test-pack configuration per user/sheet."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SheetKey, PackConfiguration


class PackConfigService:
    """CRUD for pack configurations."""

    @staticmethod
    def _normalize_scope_value(value: str | None, *, fallback: str) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or fallback

    @staticmethod
    def _normalize_pack_value(test_pack: str | None) -> str:
        normalized_pack = str(test_pack or "").strip().lower()
        return normalized_pack or "__unknown_pack__"

    async def _get_or_create_sheet_key(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        workbook_name: str | None,
        sheet_name: str | None,
        test_pack: str | None = None,
    ) -> SheetKey:
        normalized_workbook = self._normalize_scope_value(workbook_name, fallback="__unknown_workbook__")
        normalized_sheet = self._normalize_scope_value(sheet_name, fallback="__unknown_sheet__")
        normalized_pack = self._normalize_pack_value(test_pack)

        result = await db.execute(
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
        db.add(sheet_key)
        await db.flush()
        return sheet_key

    async def get_config(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
    ) -> dict[str, Any] | None:
        sheet_key = await self._get_or_create_sheet_key(
            db,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )
        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key.id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        return dict(item.config_json or {})

    async def upsert_config(
        self,
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
        pack_config: dict[str, Any],
    ) -> dict[str, Any]:
        sheet_key = await self._get_or_create_sheet_key(
            db,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )

        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key.id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        normalized_config = dict(pack_config or {})

        if item is None:
            item = PackConfiguration(
                user_id=user_id,
                sheet_key_id=int(sheet_key.id),
                sheet_name=sheet_name,
                test_pack=test_pack,
                workbook_name=workbook_name,
                config_json=normalized_config,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
        else:
            item.sheet_key_id = int(sheet_key.id)
            item.workbook_name = workbook_name or item.workbook_name
            item.config_json = normalized_config
            item.updated_at = now

        await db.commit()
        return normalized_config


pack_config_service = PackConfigService()
