"""
Authentication, subscription management, and rate limiting.

Subscription Tiers:
- FREE: 100 requests/day, basic validation
- STANDARD: 1,000 requests/day, all test packs
- PREMIUM: 10,000 requests/day, all features + priority
- ENTERPRISE: Unlimited, custom limits

API Keys are passed via X-API-Key header.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from app.testpacks.core import normalize_pack_name


class SubscriptionTier(str, Enum):
    """Subscription tiers with different rate limits and features."""
    BORDEREAUX = "bordereaux"
    SUSTAINABILITY = "sustainability"
    DEVELOPER = "developer"
    # Legacy tier kept for backwards compatibility with historical DB rows.
    TRIAL = "trial"


def coerce_subscription_tier(value: str | SubscriptionTier) -> SubscriptionTier:
    """Normalize incoming tier values, including legacy aliases."""
    if isinstance(value, SubscriptionTier):
        if value == SubscriptionTier.TRIAL:
            return SubscriptionTier.BORDEREAUX
        return value

    normalized = str(value or "").strip().lower()
    if normalized in {"trial", "starter", "basic"}:
        return SubscriptionTier.BORDEREAUX
    if normalized in {"dev", "developer", "internal"}:
        return SubscriptionTier.DEVELOPER
    if normalized == "sustainability":
        return SubscriptionTier.SUSTAINABILITY
    return SubscriptionTier.BORDEREAUX if normalized == "" else SubscriptionTier(normalized)


@dataclass
class TierConfig:
    """Configuration for a subscription tier."""
    requests_per_day: int
    requests_per_minute: int
    max_cells_per_request: int
    allowed_packs: list[str] | None  # None = all packs allowed
    priority: int  # Higher = more priority in queue


# Tier configurations
TIER_CONFIGS: dict[SubscriptionTier, TierConfig] = {
    SubscriptionTier.BORDEREAUX: TierConfig(
        requests_per_day=500,
        requests_per_minute=50,
        max_cells_per_request=10000,
        allowed_packs=["risk_and_premium", "claims"],
        priority=2,
    ),
    SubscriptionTier.SUSTAINABILITY: TierConfig(
        requests_per_day=500,
        requests_per_minute=50,
        max_cells_per_request=10000,
        allowed_packs=["csrd", "tcfd"],
        priority=2,
    ),
    SubscriptionTier.DEVELOPER: TierConfig(
        requests_per_day=1_000_000,
        requests_per_minute=10_000,
        max_cells_per_request=1_000_000,
        allowed_packs=None,
        priority=99,
    ),
    SubscriptionTier.TRIAL: TierConfig(
        requests_per_day=500,
        requests_per_minute=50,
        max_cells_per_request=10000,
        allowed_packs=["risk_and_premium", "claims", "csrd", "tcfd"],
        priority=2,
    ),
}

ADMIN_TIER_CONFIG = TierConfig(
    requests_per_day=1_000_000,
    requests_per_minute=10_000,
    max_cells_per_request=1_000_000,
    allowed_packs=None,
    priority=99,
)


@dataclass
class Subscription:
    """A user's subscription details."""
    api_key: str
    api_key_hash: str
    tier: SubscriptionTier
    owner_email: str
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def config(self) -> TierConfig:
        if self.metadata.get("is_admin"):
            return ADMIN_TIER_CONFIG
        return TIER_CONFIGS.get(self.tier, TIER_CONFIGS[SubscriptionTier.BORDEREAUX])

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


@dataclass
class RateLimitState:
    """Tracks rate limit state for a subscription."""
    minute_requests: list[float] = field(default_factory=list)
    day_requests: list[float] = field(default_factory=list)

    def clean_old_requests(self) -> None:
        """Remove requests older than the tracking window."""
        now = time.time()
        minute_ago = now - 60
        day_ago = now - 86400

        self.minute_requests = [t for t in self.minute_requests if t > minute_ago]
        self.day_requests = [t for t in self.day_requests if t > day_ago]

    def record_request(self) -> None:
        """Record a new request."""
        now = time.time()
        self.minute_requests.append(now)
        self.day_requests.append(now)

    @property
    def requests_this_minute(self) -> int:
        self.clean_old_requests()
        return len(self.minute_requests)

    @property
    def requests_today(self) -> int:
        self.clean_old_requests()
        return len(self.day_requests)


class SubscriptionStore:
    """
    In-memory subscription store.
    
    In production, replace with a database (PostgreSQL, Redis, etc.)
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}  # hash -> subscription
        self._rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)
        
        # Create a default development API key
        self._create_dev_key()

    def _hash_key(self, api_key: str) -> str:
        """Hash an API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def _create_dev_key(self) -> None:
        """Create a development API key for testing."""
        dev_key = "dev_bordereaux_key_12345"
        key_hash = self._hash_key(dev_key)
        self._subscriptions[key_hash] = Subscription(
            api_key=dev_key,
            api_key_hash=key_hash,
            tier=SubscriptionTier.DEVELOPER,
            owner_email="dev@example.com",
            created_at=datetime.utcnow(),
            expires_at=None,
            is_active=True,
            metadata={"is_dev_key": True},
        )

    def generate_api_key(
        self,
        tier: SubscriptionTier,
        owner_email: str,
        expires_in_days: int | None = None,
    ) -> str:
        """Generate a new API key for a subscription."""
        # Generate a secure random key
        prefix = tier.value[:3]
        random_part = secrets.token_urlsafe(32)
        api_key = f"bx_{prefix}_{random_part}"
        
        key_hash = self._hash_key(api_key)
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        self._subscriptions[key_hash] = Subscription(
            api_key=api_key[:12] + "...",
            api_key_hash=key_hash,
            tier=tier,
            owner_email=owner_email,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            is_active=True,
        )
        
        return api_key

    def get_subscription(self, api_key: str) -> Subscription | None:
        """Look up a subscription by API key."""
        key_hash = self._hash_key(api_key)
        return self._subscriptions.get(key_hash)

    def revoke_key(self, api_key: str) -> bool:
        """Revoke an API key."""
        key_hash = self._hash_key(api_key)
        if key_hash in self._subscriptions:
            self._subscriptions[key_hash].is_active = False
            return True
        return False

    def get_rate_limit_state(self, api_key: str) -> RateLimitState:
        """Get the rate limit state for an API key."""
        key_hash = self._hash_key(api_key)
        return self._rate_limits[key_hash]

    def check_rate_limit(self, subscription: Subscription) -> tuple[bool, str | None]:
        """
        Check if a request is within rate limits.
        
        Returns:
            (allowed, error_message)
        """
        state = self.get_rate_limit_state(subscription.api_key_hash)
        config = subscription.config

        # Check minute limit
        if state.requests_this_minute >= config.requests_per_minute:
            retry_after = 60 - (time.time() % 60)
            return False, f"Rate limit exceeded. {config.requests_per_minute} requests/minute allowed. Retry after {int(retry_after)}s"

        # Check daily limit
        if state.requests_today >= config.requests_per_day:
            # Calculate time until midnight UTC
            now = datetime.utcnow()
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            retry_after = (midnight - now).seconds
            return False, f"Daily limit exceeded. {config.requests_per_day} requests/day allowed. Resets in {retry_after // 3600}h {(retry_after % 3600) // 60}m"

        return True, None

    def record_request(self, subscription: Subscription) -> None:
        """Record a request for rate limiting."""
        state = self.get_rate_limit_state(subscription.api_key_hash)
        state.record_request()

    def get_usage_stats(self, api_key_or_hash: str) -> dict[str, Any]:
        """Get usage statistics for an API key or key hash."""
        # Try to get subscription by key first, then assume it's a hash
        subscription = self.get_subscription(api_key_or_hash)
        if subscription:
            key_hash = subscription.api_key_hash
        else:
            # Assume it's already a hash
            key_hash = api_key_or_hash
            # Find subscription by hash
            subscription = self._subscriptions.get(key_hash)
            if not subscription:
                return {}

        state = self.get_rate_limit_state(key_hash)
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


# Global subscription store (replace with DI in production)
subscription_store = SubscriptionStore()


# FastAPI security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str:
    """Extract and validate API key from request."""
    # Also check query param for easier testing
    if not api_key:
        api_key = request.query_params.get("api_key")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide via X-API-Key header or api_key query parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return api_key


async def get_current_subscription(
    api_key: str = Depends(get_api_key),
) -> Subscription:
    """Validate API key and return subscription."""
    subscription = subscription_store.get_subscription(api_key)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not subscription.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been revoked.",
        )

    if subscription.is_expired:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription has expired.",
        )

    return subscription


async def check_rate_limit(
    subscription: Subscription = Depends(get_current_subscription),
) -> Subscription:
    """Check rate limits for the current subscription."""
    allowed, error_message = subscription_store.check_rate_limit(subscription)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message,
            headers={"Retry-After": "60"},
        )

    # Record the request
    subscription_store.record_request(subscription)
    
    return subscription


def check_pack_access(subscription: Subscription, requested_packs: list[str]) -> None:
    """Verify subscription has access to requested test packs."""
    allowed_packs = get_subscription_allowed_packs(subscription)
    
    if allowed_packs is None:
        return  # All packs allowed
    
    normalized_allowed = {normalize_pack_name(pack) for pack in allowed_packs}

    for pack in requested_packs:
        normalized_pack = normalize_pack_name(pack)
        if normalized_pack not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Pack '{normalized_pack or pack}' is not available on the {subscription.tier.value} tier. "
                       f"Upgrade to access more test packs.",
            )


def get_subscription_allowed_packs(subscription: Subscription) -> list[str] | None:
    """
    Resolve the list of packs available for a subscription.

    Priority:
    1) Metadata override (`allowed_packs_override`) from persisted subscription data
    2) Tier configuration defaults
    """
    override = subscription.metadata.get("allowed_packs_override")
    raw_allowed = override if override is not None else subscription.config.allowed_packs

    if raw_allowed is None:
        return None

    normalized_allowed: list[str] = []
    seen: set[str] = set()
    for pack_name in raw_allowed:
        normalized = normalize_pack_name(pack_name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_allowed.append(normalized)

    return normalized_allowed


def check_cell_limit(subscription: Subscription, cell_count: int) -> None:
    """Verify request is within cell count limits."""
    max_cells = subscription.config.max_cells_per_request
    
    if cell_count > max_cells:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request exceeds cell limit. {cell_count} cells requested, "
                   f"but {subscription.tier.value} tier allows max {max_cells} cells per request.",
        )
