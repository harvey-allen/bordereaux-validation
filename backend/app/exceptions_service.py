"""
Exception management service for organisation-level exception handling.

Provides CRUD operations for exceptions scoped by organisation_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Exception as ExceptionModel, ExceptionStatus


class ExceptionService:
    """Service for managing exceptions at organisation level."""

    @staticmethod
    async def create_exception(
        session: AsyncSession,
        organisation_id: int,
        exception_id: str,
        description: str,
        linked_field: Optional[str] = None,
        linked_umr: Optional[str] = None,
        test_id: Optional[str] = None,
        status: str = ExceptionStatus.TODO,
        author_id: Optional[int] = None,
    ) -> ExceptionModel:
        """
        Create a new exception.

        Args:
            session: Database session
            organisation_id: Organisation ID
            exception_id: Unique exception identifier within the organisation
            description: Exception description
            linked_field: Optional linked field from selected test pack
            linked_umr: Optional linked UMR value
            test_id: Legacy linked test ID (fallback)
            status: Exception status (defaults to TODO)
            author_id: Optional user ID of the creator

        Returns:
            Created Exception model
        """
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
    async def get_exceptions(
        session: AsyncSession,
        organisation_id: int,
        linked_field: Optional[str] = None,
        linked_umr: Optional[str] = None,
        test_id: Optional[str] = None,
    ) -> list[ExceptionModel]:
        """
        Get all exceptions for an organisation, optionally filtered by linked field/UMR.

        Args:
            session: Database session
            organisation_id: Organisation ID
            linked_field: Optional linked field to filter by
            linked_umr: Optional linked UMR to filter by
            test_id: Legacy test ID filter (mapped to linked_field fallback)

        Returns:
            List of Exception models
        """
        query = select(ExceptionModel).where(
            ExceptionModel.organisation_id == organisation_id
        )
        if linked_field:
            query = query.where(ExceptionModel.linked_field == linked_field)
        elif test_id:
            query = query.where(ExceptionModel.linked_field == test_id)
        if linked_umr:
            query = query.where(ExceptionModel.linked_umr == linked_umr)
        
        result = await session.execute(query.order_by(ExceptionModel.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def get_exception_by_id(
        session: AsyncSession,
        organisation_id: int,
        exception_id: str,
    ) -> Optional[ExceptionModel]:
        """
        Get a specific exception by ID within an organisation.

        Args:
            session: Database session
            organisation_id: Organisation ID
            exception_id: Exception ID

        Returns:
            Exception model or None if not found
        """
        query = select(ExceptionModel).where(
            and_(
                ExceptionModel.organisation_id == organisation_id,
                ExceptionModel.exception_id == exception_id,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_exception_by_db_id(
        session: AsyncSession,
        db_id: int,
        organisation_id: int,
    ) -> Optional[ExceptionModel]:
        """
        Get a specific exception by database ID within an organisation.

        Args:
            session: Database session
            db_id: Database ID
            organisation_id: Organisation ID

        Returns:
            Exception model or None if not found
        """
        query = select(ExceptionModel).where(
            and_(
                ExceptionModel.id == db_id,
                ExceptionModel.organisation_id == organisation_id,
            )
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def update_exception(
        session: AsyncSession,
        organisation_id: int,
        exception_id: str,
        description: Optional[str] = None,
        linked_field: Optional[str] = None,
        linked_umr: Optional[str] = None,
        test_id: Optional[str] = None,
        update_linked_field: bool = False,
        update_linked_umr: bool = False,
        status: Optional[str] = None,
    ) -> Optional[ExceptionModel]:
        """
        Update an exception.

        Args:
            session: Database session
            organisation_id: Organisation ID
            exception_id: Exception ID
            description: Updated description
            linked_field: Updated linked field
            linked_umr: Updated linked UMR
            test_id: Legacy updated test ID (fallback)
            update_linked_field: Whether to apply linked-field update (supports clearing)
            update_linked_umr: Whether to apply linked-UMR update (supports clearing)
            status: Updated status

        Returns:
            Updated Exception model or None if not found
        """
        exception = await ExceptionService.get_exception_by_id(
            session, organisation_id, exception_id
        )
        if not exception:
            return None

        if description is not None:
            exception.description = description
        if update_linked_field:
            exception.linked_field = linked_field if linked_field is not None else test_id
        if update_linked_umr:
            exception.linked_umr = linked_umr
        if status is not None:
            exception.status = status
        
        exception.updated_at = datetime.now(timezone.utc)
        session.add(exception)
        await session.flush()
        return exception

    @staticmethod
    async def delete_exception(
        session: AsyncSession,
        organisation_id: int,
        exception_id: str,
    ) -> bool:
        """
        Delete an exception.

        Args:
            session: Database session
            organisation_id: Organisation ID
            exception_id: Exception ID

        Returns:
            True if deleted, False if not found
        """
        exception = await ExceptionService.get_exception_by_id(
            session, organisation_id, exception_id
        )
        if not exception:
            return False

        await session.delete(exception)
        await session.flush()
        return True


# Singleton instance
exception_service = ExceptionService()
