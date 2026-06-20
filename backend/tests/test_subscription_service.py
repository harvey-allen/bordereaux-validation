from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.auth import Subscription, SubscriptionTier
from app.services.subscription.subscription_service import (
    SubscriptionService,
    SubscriptionRepository,
    generate_api_key,
    hash_api_key,
)


def test_hash_and_generate_api_key_prefixes():
    hashed = hash_api_key("abc")
    assert len(hashed) == 64
    assert hashed == hash_api_key("abc")

    generated = generate_api_key(SubscriptionTier.BORDEREAUX)
    assert generated.startswith("bx_bor_")


def test_get_or_create_organisation_id_creates_when_missing(monkeypatch):
    service = SubscriptionService()

    monkeypatch.setattr(
        SubscriptionRepository,
        "get_organisation_by_name",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        SubscriptionRepository,
        "create_organisation",
        AsyncMock(return_value=SimpleNamespace(id=42)),
    )

    organisation_id = asyncio.run(
        service._get_or_create_organisation_id(
            AsyncMock(),
            email="person@Example.com",
            organisation_name="",
        )
    )

    assert organisation_id == 42


def test_get_or_create_subscription_returns_existing_user(monkeypatch):
    service = SubscriptionService()
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    existing = SimpleNamespace(
        id=7,
        organisation_id=11,
        excel_user_id="excel_1",
        email="user@example.com",
        display_name="User",
        api_key_hash="hash_1",
        api_key_prefix="bx_123...",
        tier="developer",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        extra_data=None,
    )

    monkeypatch.setattr(
        SubscriptionRepository,
        "get_user_by_excel_user_id",
        AsyncMock(return_value=existing),
    )

    subscription, api_key = asyncio.run(
        service.get_or_create_subscription(
            db,
            excel_user_id="excel_1",
            email="user@example.com",
            display_name="User",
        )
    )

    assert api_key == ""
    assert subscription.owner_email == "user@example.com"
    assert subscription.metadata["organisation_id"] == 11


def test_get_subscription_by_api_key_uses_cache_when_valid(monkeypatch):
    service = SubscriptionService()
    key_hash = hash_api_key("my-api-key")

    cached = Subscription(
        api_key="masked",
        api_key_hash=key_hash,
        tier=SubscriptionTier.BORDEREAUX,
        owner_email="cached@example.com",
        created_at=datetime.now(timezone.utc),
        metadata={},
    )

    service._subscription_cache[key_hash] = cached
    service._cache_ttl[key_hash] = 9999999999

    repo_lookup = AsyncMock()
    monkeypatch.setattr(SubscriptionRepository, "get_user_by_api_key_hash", repo_lookup)

    result = asyncio.run(service.get_subscription_by_api_key(AsyncMock(), "my-api-key"))

    assert result is cached
    repo_lookup.assert_not_called()


def test_check_rate_limit_uses_db_count_when_needed(monkeypatch):
    service = SubscriptionService()
    key_hash = "hash-rate"

    subscription = Subscription(
        api_key="masked",
        api_key_hash=key_hash,
        tier=SubscriptionTier.BORDEREAUX,
        owner_email="rate@example.com",
        created_at=datetime.now(timezone.utc),
        metadata={},
    )

    service._rate_limits[key_hash].day_requests = []
    service._rate_limits[key_hash].minute_requests = []

    monkeypatch.setattr(
        SubscriptionRepository,
        "count_logs_since",
        AsyncMock(return_value=subscription.config.requests_per_day),
    )

    allowed, error = asyncio.run(service.check_rate_limit(AsyncMock(), subscription))

    assert allowed is False
    assert "Daily limit exceeded" in str(error)


def test_db_to_subscription_parses_allowed_packs_override():
    service = SubscriptionService()

    db_sub = SimpleNamespace(
        id=9,
        organisation_id=2,
        excel_user_id="excel_9",
        email="ops@example.com",
        display_name="Ops",
        api_key_hash="hash-9",
        api_key_prefix="bx_dev_abc...",
        tier="developer",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        expires_at=None,
        extra_data='{"allowed_packs": ["claims", "risk_and_premium"]}',
    )

    subscription = service._db_to_subscription(db_sub)

    assert subscription.tier == SubscriptionTier.DEVELOPER
    assert subscription.metadata["allowed_packs_override"] == ["claims", "risk_and_premium"]
