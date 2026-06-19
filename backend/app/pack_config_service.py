"""Service for persisted test-pack configuration per user/sheet."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.configuration.pack_config_repository import PackConfigRepository
from app.services.configuration.field_mapping_service import field_mapping_service


class PackConfigService:
    """CRUD for pack configurations."""

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
        return await PackConfigRepository.get_config(
            db,
            organisation_id=organisation_id,
            user_id=user_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
        )

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
        return await PackConfigRepository.upsert_config(
            db,
            organisation_id=organisation_id,
            user_id=user_id,
            workbook_name=workbook_name,
            sheet_name=sheet_name,
            test_pack=test_pack,
            pack_config=pack_config,
        )


pack_config_service = PackConfigService()


async def estimate_field_mapping(
    test_pack: str,
    territory: str,
    headers: list[str],
    mandatory_fields: list[str],
) -> dict[str, Any]:
    return await field_mapping_service.estimate_field_mapping(
        test_pack=test_pack,
        territory=territory,
        headers=headers,
        mandatory_fields=mandatory_fields,
    )

