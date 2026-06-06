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
            test_id: Optional linked test ID from rules engine
            status: Exception status (defaults to TODO)
            author_id: Optional user ID of the creator

        Returns:
            Created Exception model
        """
        exception = ExceptionModel(
            organisation_id=organisation_id,
            exception_id=exception_id,
            description=description,
            test_id=test_id,
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
        test_id: Optional[str] = None,
    ) -> list[ExceptionModel]:
        """
        Get all exceptions for an organisation, optionally filtered by test_id.

        Args:
            session: Database session
            organisation_id: Organisation ID
            test_id: Optional test ID to filter by

        Returns:
            List of Exception models
        """
        query = select(ExceptionModel).where(
            ExceptionModel.organisation_id == organisation_id
        )
        if test_id:
            query = query.where(ExceptionModel.test_id == test_id)
        
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
        test_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[ExceptionModel]:
        """
        Update an exception.

        Args:
            session: Database session
            organisation_id: Organisation ID
            exception_id: Exception ID
            description: Updated description
            test_id: Updated test ID
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
        if test_id is not None:
            exception.test_id = test_id
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
