from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Organisation, RequestLog, UserSubscription


class SubscriptionRepository:
    """Persistence operations for subscription and request-log records."""

    @staticmethod
    async def get_user_by_excel_user_id(db: AsyncSession, *, excel_user_id: str) -> UserSubscription | None:
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_api_key_hash(db: AsyncSession, *, api_key_hash: str) -> UserSubscription | None:
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.api_key_hash == api_key_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email_active_latest(db: AsyncSession, *, email: str) -> UserSubscription | None:
        result = await db.execute(
            select(UserSubscription)
            .where(func.lower(UserSubscription.email) == email)
            .where(UserSubscription.is_active.is_(True))
            .order_by(UserSubscription.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def get_organisation_by_name(db: AsyncSession, *, name: str) -> Organisation | None:
        result = await db.execute(
            select(Organisation).where(func.lower(Organisation.name) == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_organisation(db: AsyncSession, *, name: str) -> Organisation:
        org = Organisation(name=name, created_at=datetime.now(timezone.utc))
        db.add(org)
        await db.flush()
        return org

    @staticmethod
    async def create_user_subscription(
        db: AsyncSession,
        *,
        organisation_id: int,
        excel_user_id: str,
        email: str,
        display_name: str | None,
        api_key_hash: str,
        api_key_prefix: str,
        tier,
        is_active: bool,
    ) -> UserSubscription:
        sub = UserSubscription(
            organisation_id=organisation_id,
            excel_user_id=excel_user_id,
            email=email,
            display_name=display_name,
            api_key_hash=api_key_hash,
            api_key_prefix=api_key_prefix,
            tier=tier,
            is_active=is_active,
            created_at=datetime.now(timezone.utc),
        )
        db.add(sub)
        await db.flush()
        return sub

    @staticmethod
    async def count_logs_since(db: AsyncSession, *, api_key_hash: str, start_time: datetime) -> int:
        result = await db.execute(
            select(func.count(RequestLog.id))
            .where(RequestLog.api_key_hash == api_key_hash)
            .where(RequestLog.timestamp >= start_time)
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def insert_request_log(
        db: AsyncSession,
        *,
        api_key_hash: str,
        endpoint: str | None,
        cell_count: int | None,
    ) -> None:
        log = RequestLog(
            api_key_hash=api_key_hash,
            timestamp=datetime.now(timezone.utc),
            endpoint=endpoint,
            cell_count=cell_count,
        )
        db.add(log)

    @staticmethod
    async def purge_request_logs_before(db: AsyncSession, *, cutoff: datetime) -> None:
        await db.execute(delete(RequestLog).where(RequestLog.timestamp < cutoff))

    @staticmethod
    async def delete_request_logs_before(db: AsyncSession, *, cutoff: datetime) -> int:
        result = await db.execute(delete(RequestLog).where(RequestLog.timestamp < cutoff))
        return int(result.rowcount or 0)
