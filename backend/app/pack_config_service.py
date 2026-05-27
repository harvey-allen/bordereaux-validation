"""Service for persisted test-pack configuration per user/sheet."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import PackConfiguration


class PackConfigService:
    """CRUD for pack configurations."""

    async def get_config(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        sheet_name: str,
        test_pack: str,
    ) -> dict[str, Any] | None:
        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_name == sheet_name)
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
        user_id: int,
        sheet_name: str,
        test_pack: str,
        pack_config: dict[str, Any],
        workbook_name: str | None = None,
    ) -> dict[str, Any]:
        result = await db.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_name == sheet_name)
            .where(PackConfiguration.test_pack == test_pack)
        )
        item = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        normalized_config = dict(pack_config or {})

        if item is None:
            item = PackConfiguration(
                user_id=user_id,
                sheet_name=sheet_name,
                test_pack=test_pack,
                workbook_name=workbook_name,
                config_json=normalized_config,
                created_at=now,
                updated_at=now,
            )
            db.add(item)
        else:
            item.workbook_name = workbook_name or item.workbook_name
            item.config_json = normalized_config
            item.updated_at = now

        await db.commit()
        return normalized_config


pack_config_service = PackConfigService()
