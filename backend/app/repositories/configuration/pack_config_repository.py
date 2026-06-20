from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import PackConfiguration
from app.repositories.shared.sheet_key_repository import SheetKeyRepository


class PackConfigRepository:
    """Persistence operations for pack configuration records."""

    @staticmethod
    async def get_config(
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
    ) -> dict[str, Any] | None:
        sheet_key = await SheetKeyRepository.find(
            db,
            organisation_id=organisation_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )
        if sheet_key is None:
            return None

        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key.id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()
        return dict(item.config_json or {}) if item else None

    @staticmethod
    async def upsert_config(
        db: AsyncSession,
        *,
        organisation_id: int,
        user_id: int,
        workbook_name: str | None,
        sheet_name: str,
        test_pack: str,
        pack_config: dict[str, Any],
    ) -> dict[str, Any]:
        sheet_key = await SheetKeyRepository.get_or_create(
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
