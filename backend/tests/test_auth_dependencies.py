from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import Subscription, SubscriptionTier, subscription_store
from app.common.auth import dependencies as auth_deps


def _request(*, headers: dict[str, str] | None = None, query_string: str = "") -> Request:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/subscription",
        "headers": encoded_headers,
        "query_string": query_string.encode("latin-1"),
    }
    return Request(scope)


def test_normalize_email_trims_and_lowercases():
    assert auth_deps._normalize_email("  User@Example.COM ") == "user@example.com"
    assert auth_deps._normalize_email(None) == ""


def test_get_authenticated_subscription_uses_api_key_fallback():
    request = _request(headers={"X-API-Key": "dev_bordereaux_key_12345"})

    subscription = asyncio.run(auth_deps.get_authenticated_subscription(request, db=None))

    assert subscription.tier == SubscriptionTier.DEVELOPER


def test_get_authenticated_subscription_raises_for_missing_credentials():
    request = _request()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.get_authenticated_subscription(request, db=None))

    assert exc.value.status_code == 401
    assert "Missing API key or Excel user email" in exc.value.detail


def test_enforce_rate_limit_db_path_records_request(monkeypatch):
    request = _request(headers={"X-API-Key": "dev_bordereaux_key_12345"})
    db = AsyncMock()
    subscription = Subscription(
        api_key="masked",
        api_key_hash="hash-123",
        tier=SubscriptionTier.BORDEREAUX,
        owner_email="db@example.com",
        created_at=datetime.now(timezone.utc),
        metadata={"is_dev_key": False},
    )

    check_rate_limit = AsyncMock(return_value=(True, None))
    record_request = AsyncMock()

    monkeypatch.setattr(auth_deps, "DB_AVAILABLE", True)
    monkeypatch.setattr(auth_deps.subscription_service, "check_rate_limit", check_rate_limit)
    monkeypatch.setattr(auth_deps.subscription_service, "record_request", record_request)

    result = asyncio.run(auth_deps.enforce_rate_limit(request, subscription=subscription, db=db))

    assert result is subscription
    check_rate_limit.assert_awaited_once()
    record_request.assert_awaited_once()


def test_enforce_rate_limit_fallback_path_blocks_when_exceeded(monkeypatch):
    request = _request(headers={"X-API-Key": "dev_bordereaux_key_12345"})
    subscription = subscription_store.get_subscription("dev_bordereaux_key_12345")

    monkeypatch.setattr(auth_deps, "DB_AVAILABLE", False)
    monkeypatch.setattr(subscription_store, "check_rate_limit", lambda _subscription: (False, "Too many requests"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_deps.enforce_rate_limit(request, subscription=subscription, db=None))

    assert exc.value.status_code == 429
    assert "Too many requests" in str(exc.value.detail)
