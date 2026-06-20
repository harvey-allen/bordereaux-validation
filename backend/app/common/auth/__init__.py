"""Auth sub-package.

Re-exports the public API of app.auth so that new code can import from the
canonical path ``app.common.auth`` while existing imports still work unchanged.

Usage
-----
    from app.common.auth import Subscription, SubscriptionTier, subscription_store
"""
from __future__ import annotations

from app.auth import (
    RateLimitState,
    Subscription,
    SubscriptionStore,
    SubscriptionTier,
    TierConfig,
    check_cell_limit,
    check_pack_access,
    coerce_subscription_tier,
    get_subscription_allowed_packs,
    subscription_store,
)
from app.common.auth.dependencies import enforce_rate_limit, get_authenticated_subscription

__all__ = [
    "RateLimitState",
    "Subscription",
    "SubscriptionStore",
    "SubscriptionTier",
    "TierConfig",
    "check_cell_limit",
    "check_pack_access",
    "coerce_subscription_tier",
    "get_subscription_allowed_packs",
    "subscription_store",
    "get_authenticated_subscription",
    "enforce_rate_limit",
]
