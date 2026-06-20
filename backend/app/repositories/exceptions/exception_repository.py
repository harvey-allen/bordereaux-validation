from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Exception as ExceptionModel, ExceptionStatus


class ExceptionRepository:
    """Persistence operations for organisation-scoped exceptions."""

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        organisation_id: int,
        exception_id: str,
        description: str,
        linked_field: Optional[str] = None,
        linked_umr: Optional[str] = None,
        test_id: Optional[str] = None,
        status: str = ExceptionStatus.TODO,
        author_id: Optional[int] = None,
    ) -> ExceptionModel:
        exception = ExceptionModel(
            organisation_id=organisation_id,
            exception_id=exception_id,
            description=description,
            linked_field=linked_field or test_id,
            linked_umr=linked_umr,
            status=status,
            author_id=author_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(exception)
        await session.flush()
        return exception

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        organisation_id: int,
        linked_field: Optional[str] = None,
        linked_umr: Optional[str] = None,
        test_id: Optional[str] = None,
    ) -> list[ExceptionModel]:
        query = select(ExceptionModel).where(ExceptionModel.organisation_id == organisation_id)
        if linked_field:
            query = query.where(ExceptionModel.linked_field == linked_field)
        elif test_id:
            query = query.where(ExceptionModel.linked_field == test_id)
        if linked_umr:
            query = query.where(ExceptionModel.linked_umr == linked_umr)

        result = await session.execute(query.order_by(ExceptionModel.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def get_by_exception_id(
        session: AsyncSession,
        *,
        organisation_id: int,
        exception_id: str,
    ) -> Optional[ExceptionModel]:
        query = select(ExceptionModel).where(
            and_(
                ExceptionModel.organisation_id == organisation_id,
                ExceptionModel.exception_id == exception_id,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_db_id(
        session: AsyncSession,
        *,
        db_id: int,
        organisation_id: int,
    ) -> Optional[ExceptionModel]:
        query = select(ExceptionModel).where(
            and_(
                ExceptionModel.id == db_id,
                ExceptionModel.organisation_id == organisation_id,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_by_exception_id(
        session: AsyncSession,
        *,
        organisation_id: int,
        exception_id: str,
    ) -> bool:
        exception = await ExceptionRepository.get_by_exception_id(
            session,
            organisation_id=organisation_id,
            exception_id=exception_id,
        )
        if not exception:
            return False

        await session.delete(exception)
        await session.flush()
        return True
