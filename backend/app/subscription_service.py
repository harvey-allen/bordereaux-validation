"""
Subscription service for managing user subscriptions in PostgreSQL.

Handles:
- Creating subscriptions for new Excel users
- Looking up subscriptions by API key or Excel user ID
- Rate limit tracking
- Subscription upgrades/downgrades
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import RateLimitState, Subscription, SubscriptionTier, coerce_subscription_tier
from app.database import Organisation, RequestLog, UserSubscription


# Get default tier from environment
DEFAULT_TIER = coerce_subscription_tier(os.getenv("DEFAULT_SUBSCRIPTION_TIER", "bordereaux"))
ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "harveyallen2001@gmail.com").split(",")
    if email.strip()
}


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key(tier: SubscriptionTier) -> str:
    """Generate a new API key."""
    prefix = tier.value[:3]
    random_part = secrets.token_urlsafe(32)
    return f"bx_{prefix}_{random_part}"


class SubscriptionService:
    """
    Service for managing subscriptions in PostgreSQL.
    
    Combines database persistence with in-memory rate limiting for performance.
    """

    def __init__(self) -> None:
        # In-memory rate limit cache (cleared on restart, but that's okay)
        self._rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)
        # Cache of subscriptions for performance
        self._subscription_cache: dict[str, Subscription] = {}
        self._cache_ttl: dict[str, float] = {}
        self._cache_duration = 300  # 5 minutes
        # Track the last date request logs were purged so we purge once per day
        self._last_purge_date: str | None = None

    def _is_cache_valid(self, key_hash: str) -> bool:
        """Check if cached subscription is still valid."""
        if key_hash not in self._cache_ttl:
            return False
        return time.time() < self._cache_ttl[key_hash]

    def _cache_subscription(self, subscription: Subscription) -> None:
        """Cache a subscription for faster lookups."""
        self._subscription_cache[subscription.api_key_hash] = subscription
        self._cache_ttl[subscription.api_key_hash] = time.time() + self._cache_duration

    async def _get_or_create_organisation_id(
        self,
        db: AsyncSession,
        *,
        email: str,
        organisation_name: str | None = None,
    ) -> int:
        normalized = (organisation_name or "").strip().lower()
        if not normalized:
            domain = email.strip().lower().split("@")[-1] if "@" in email else "default"
            normalized = domain or "default"

        result = await db.execute(
            select(Organisation).where(func.lower(Organisation.name) == normalized)
        )
        organisation = result.scalar_one_or_none()
        if organisation is None:
            organisation = Organisation(name=normalized, created_at=datetime.now(timezone.utc))
            db.add(organisation)
            await db.flush()
        return int(organisation.id)

    async def get_or_create_subscription(
        self,
        db: AsyncSession,
        excel_user_id: str,
        email: str,
        display_name: str | None = None,
        organisation_name: str | None = None,
    ) -> tuple[Subscription, str]:
        """
        Get existing subscription or create a new one for an Excel user.
        
        Returns:
            (Subscription, api_key) - api_key is only returned for new subscriptions
        """
        # Check for existing subscription
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        db_sub = result.scalar_one_or_none()

        if db_sub:
            if db_sub.organisation_id is None:
                db_sub.organisation_id = await self._get_or_create_organisation_id(
                    db,
                    email=email,
                    organisation_name=organisation_name,
                )
                await db.commit()
                await db.refresh(db_sub)
            # Return existing subscription (api_key is not returned for security)
            subscription = self._db_to_subscription(db_sub)
            self._cache_subscription(subscription)
            return subscription, ""

        # Create new subscription
        api_key = generate_api_key(DEFAULT_TIER)
        key_hash = hash_api_key(api_key)

        organisation_id = await self._get_or_create_organisation_id(
            db,
            email=email,
            organisation_name=organisation_name,
        )

        db_sub = UserSubscription(
            organisation_id=organisation_id,
            excel_user_id=excel_user_id,
            email=email,
            display_name=display_name,
            api_key_hash=key_hash,
            api_key_prefix=api_key[:12] + "...",
            tier=DEFAULT_TIER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(db_sub)
        await db.commit()
        await db.refresh(db_sub)

        subscription = self._db_to_subscription(db_sub)
        self._cache_subscription(subscription)
        
        return subscription, api_key

    async def get_subscription_by_api_key(
        self,
        db: AsyncSession,
        api_key: str,
    ) -> Subscription | None:
        """Look up a subscription by API key."""
        key_hash = hash_api_key(api_key)

        # Check cache first
        if self._is_cache_valid(key_hash):
            return self._subscription_cache.get(key_hash)

        # Query database
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.api_key_hash == key_hash)
        )
        db_sub = result.scalar_one_or_none()

        if not db_sub:
            return None

        # Update last_used_at
        db_sub.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        subscription = self._db_to_subscription(db_sub)
        self._cache_subscription(subscription)
        
        return subscription

    async def get_subscription_by_excel_user(
        self,
        db: AsyncSession,
        excel_user_id: str,
    ) -> Subscription | None:
        """Look up a subscription by Excel user ID."""
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        db_sub = result.scalar_one_or_none()

        if not db_sub:
            return None

        subscription = self._db_to_subscription(db_sub)
        self._cache_subscription(subscription)
        
        return subscription

    async def get_subscription_by_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> Subscription | None:
        """Look up an active subscription by email (case-insensitive)."""
        normalized_email = email.strip().lower()
        if not normalized_email:
            return None

        result = await db.execute(
            select(UserSubscription)
            .where(func.lower(UserSubscription.email) == normalized_email)
            .where(UserSubscription.is_active.is_(True))
            .order_by(UserSubscription.created_at.desc())
        )
        db_sub = result.scalars().first()

        if not db_sub and normalized_email in ADMIN_EMAILS:
            api_key = generate_api_key(DEFAULT_TIER)
            key_hash = hash_api_key(api_key)
            excel_user_id = f"excel_{normalized_email.replace('@', '_at_').replace('.', '_')}"
            organisation_id = await self._get_or_create_organisation_id(
                db,
                email=normalized_email,
                organisation_name=None,
            )
            db_sub = UserSubscription(
                organisation_id=organisation_id,
                excel_user_id=excel_user_id,
                email=normalized_email,
                display_name="Harvey Allen",
                api_key_hash=key_hash,
                api_key_prefix=api_key[:12] + "...",
                tier=SubscriptionTier.DEVELOPER,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(db_sub)
            await db.commit()
            await db.refresh(db_sub)

        if not db_sub:
            return None

        # Backfill organisation_id for users created before the migration
        if db_sub.organisation_id is None:
            db_sub.organisation_id = await self._get_or_create_organisation_id(
                db,
                email=db_sub.email,
                organisation_name=None,
            )

        db_sub.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        subscription = self._db_to_subscription(db_sub)
        self._cache_subscription(subscription)
        return subscription

    async def update_tier(
        self,
        db: AsyncSession,
        excel_user_id: str,
        new_tier: SubscriptionTier,
    ) -> Subscription | None:
        """Update a user's subscription tier."""
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        db_sub = result.scalar_one_or_none()

        if not db_sub:
            return None

        db_sub.tier = new_tier
        await db.commit()
        await db.refresh(db_sub)

        # Invalidate cache
        if db_sub.api_key_hash in self._subscription_cache:
            del self._subscription_cache[db_sub.api_key_hash]
            del self._cache_ttl[db_sub.api_key_hash]

        subscription = self._db_to_subscription(db_sub)
        self._cache_subscription(subscription)
        
        return subscription

    async def regenerate_api_key(
        self,
        db: AsyncSession,
        excel_user_id: str,
    ) -> str | None:
        """Generate a new API key for a user (invalidates old key)."""
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        db_sub = result.scalar_one_or_none()

        if not db_sub:
            return None

        # Invalidate old cache
        old_hash = db_sub.api_key_hash
        if old_hash in self._subscription_cache:
            del self._subscription_cache[old_hash]
            del self._cache_ttl[old_hash]

        # Generate new key
        new_api_key = generate_api_key(coerce_subscription_tier(db_sub.tier))
        db_sub.api_key_hash = hash_api_key(new_api_key)
        db_sub.api_key_prefix = new_api_key[:12] + "..."
        
        await db.commit()
        
        return new_api_key

    async def record_request(
        self,
        db: AsyncSession,
        subscription: Subscription,
        endpoint: str | None = None,
        cell_count: int | None = None,
    ) -> None:
        """Record a request for rate limiting."""
        # In-memory rate limiting (fast)
        state = self._rate_limits[subscription.api_key_hash]
        state.record_request()

        # Async database logging (for persistence/analytics)
        log = RequestLog(
            api_key_hash=subscription.api_key_hash,
            timestamp=datetime.now(timezone.utc),
            endpoint=endpoint,
            cell_count=cell_count,
        )
        db.add(log)

        # On the first request of each new UTC day, purge logs older than yesterday.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._last_purge_date != today:
            self._last_purge_date = today
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            await db.execute(
                delete(RequestLog).where(RequestLog.timestamp < day_start)
            )

        await db.commit()

    async def check_rate_limit(
        self,
        db: AsyncSession,
        subscription: Subscription,
    ) -> tuple[bool, str | None]:
        """
        Check if a request is within rate limits.
        
        Uses in-memory tracking for fast checks, with database as backup.
        """
        state = self._rate_limits[subscription.api_key_hash]
        config = subscription.config

        # Check minute limit (in-memory only for speed)
        if state.requests_this_minute >= config.requests_per_minute:
            retry_after = 60 - (time.time() % 60)
            return False, f"Rate limit exceeded. {config.requests_per_minute} requests/minute allowed. Retry after {int(retry_after)}s"

        # Check daily limit (use database for accuracy after restart)
        daily_count = state.requests_today
        
        # If in-memory count is low, verify against database
        if daily_count < config.requests_per_day // 2:
            # Check database for today's requests
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            result = await db.execute(
                select(func.count(RequestLog.id))
                .where(RequestLog.api_key_hash == subscription.api_key_hash)
                .where(RequestLog.timestamp >= today_start)
            )
            db_count = result.scalar() or 0
            daily_count = max(daily_count, db_count)

        if daily_count >= config.requests_per_day:
            now = datetime.now(timezone.utc)
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            retry_after = int((midnight - now).total_seconds())
            return False, f"Daily limit exceeded. {config.requests_per_day} requests/day allowed. Resets in {retry_after // 3600}h {(retry_after % 3600) // 60}m"

        return True, None

    def get_usage_stats(self, subscription: Subscription) -> dict[str, Any]:
        """Get usage statistics for a subscription."""
        state = self._rate_limits[subscription.api_key_hash]
        config = subscription.config

        return {
            "tier": subscription.tier.value,
            "requests_today": state.requests_today,
            "requests_this_minute": state.requests_this_minute,
            "daily_limit": config.requests_per_day,
            "minute_limit": config.requests_per_minute,
            "daily_remaining": max(0, config.requests_per_day - state.requests_today),
            "minute_remaining": max(0, config.requests_per_minute - state.requests_this_minute),
        }

    async def cleanup_old_logs(self, db: AsyncSession, days: int = 7) -> int:
        """Clean up request logs older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await db.execute(
            delete(RequestLog).where(RequestLog.timestamp < cutoff)
        )
        await db.commit()
        return result.rowcount or 0

    def _db_to_subscription(self, db_sub: UserSubscription) -> Subscription:
        """Convert database model to Subscription dataclass."""
        extra_data: dict[str, Any] = {}
        if db_sub.extra_data:
            try:
                parsed = json.loads(db_sub.extra_data)
                if isinstance(parsed, dict):
                    extra_data = parsed
            except Exception:
                extra_data = {}

        allowed_packs_override = None
        for key in ("allowed_packs", "allowedPacks", "test_packs", "testPacks"):
            value = extra_data.get(key)
            if isinstance(value, list):
                allowed_packs_override = [str(item) for item in value if str(item or "").strip()]
                break

        return Subscription(
            api_key=db_sub.api_key_prefix,
            api_key_hash=db_sub.api_key_hash,
            tier=coerce_subscription_tier(db_sub.tier) if isinstance(db_sub.tier, str) else coerce_subscription_tier(db_sub.tier),
            owner_email=db_sub.email,
            created_at=db_sub.created_at,
            expires_at=db_sub.expires_at,
            is_active=db_sub.is_active,
            metadata={
                "user_id": db_sub.id,
                "organisation_id": db_sub.organisation_id,
                "excel_user_id": db_sub.excel_user_id,
                "display_name": db_sub.display_name,
                "is_admin": db_sub.email.strip().lower() in ADMIN_EMAILS,
                "allowed_packs_override": allowed_packs_override,
            },
        )


# Global service instance
subscription_service = SubscriptionService()
