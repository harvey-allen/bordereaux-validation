from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    PackConfiguration,
    SheetKey,
    ValidationResultPayload,
    ValidationResultVersion,
    ValidationRun,
)


class ResultsRepository:
    """Persistence operations for results/version entities."""

    @staticmethod
    async def get_version_for_sheet_key_pack(
        session: AsyncSession,
        *,
        sheet_key_id: int,
        test_pack: str,
    ) -> ValidationResultVersion | None:
        result = await session.execute(
            select(ValidationResultVersion)
            .where(ValidationResultVersion.sheet_key_id == sheet_key_id)
            .where(ValidationResultVersion.test_pack == test_pack)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_version_by_id_for_org(
        session: AsyncSession,
        *,
        organisation_id: int,
        version_id: int,
    ) -> tuple[ValidationResultVersion, SheetKey] | None:
        result = await session.execute(
            select(ValidationResultVersion, SheetKey)
            .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
            .where(ValidationResultVersion.id == version_id)
            .where(SheetKey.organisation_id == organisation_id)
        )
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    @staticmethod
    async def get_version_by_sheet_key_for_org(
        session: AsyncSession,
        *,
        organisation_id: int,
        sheet_key_id: int,
    ) -> ValidationResultVersion | None:
        result = await session.execute(
            select(ValidationResultVersion)
            .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
            .where(ValidationResultVersion.sheet_key_id == sheet_key_id)
            .where(SheetKey.organisation_id == organisation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_versions_for_org_pack(
        session: AsyncSession,
        *,
        organisation_id: int,
        test_pack: str,
    ) -> list[tuple[ValidationResultVersion, SheetKey]]:
        result = await session.execute(
            select(ValidationResultVersion, SheetKey)
            .join(SheetKey, ValidationResultVersion.sheet_key_id == SheetKey.id)
            .where(SheetKey.organisation_id == organisation_id)
            .where(ValidationResultVersion.test_pack == test_pack)
            .order_by(desc(ValidationResultVersion.updated_at), desc(ValidationResultVersion.id))
        )
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def get_payload_for_version(
        session: AsyncSession,
        *,
        version_id: int,
    ) -> ValidationResultPayload | None:
        result = await session.execute(
            select(ValidationResultPayload)
            .where(ValidationResultPayload.validation_result_version_id == version_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pack_config_for_user_sheet_pack(
        session: AsyncSession,
        *,
        user_id: int,
        sheet_key_id: int,
        test_pack: str,
    ) -> PackConfiguration | None:
        result = await session.execute(
            select(PackConfiguration)
            .where(PackConfiguration.user_id == user_id)
            .where(PackConfiguration.sheet_key_id == sheet_key_id)
            .where(PackConfiguration.test_pack == test_pack)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_run_for_scope(
        session: AsyncSession,
        *,
        sheet_name: str,
        workbook_name: str | None,
        user_id: int | None,
        api_key_hash: str | None,
    ) -> ValidationRun | None:
        query = (
            select(ValidationRun)
            .where(ValidationRun.sheet_name == sheet_name)
            .order_by(desc(ValidationRun.run_timestamp))
            .limit(1)
        )

        if user_id is not None:
            query = query.where(ValidationRun.user_id == user_id)
        elif api_key_hash:
            query = query.where(ValidationRun.api_key_hash == api_key_hash)
        else:
            query = query.where(ValidationRun.user_id.is_(None))
            query = query.where(ValidationRun.api_key_hash.is_(None))

        if workbook_name:
            query = query.where(ValidationRun.workbook_name == workbook_name)

        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_run_by_token(
        session: AsyncSession,
        *,
        run_token: int,
    ) -> ValidationRun | None:
        result = await session.execute(
            select(ValidationRun).where(ValidationRun.run_token == run_token)
        )
        return result.scalar_one_or_none()
