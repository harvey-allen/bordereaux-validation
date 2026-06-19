"""Authentication and rate-limit dependencies.

This module introduces a canonical location for auth dependencies.
In Phase 2 it mirrors existing behaviour from `app.main`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.auth import Subscription, subscription_store

try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db
    from app.subscription_service import subscription_service

    DB_AVAILABLE = True
except ImportError:
    AsyncSession = None  # type: ignore[assignment]
    get_db = None  # type: ignore[assignment]
    subscription_service = None  # type: ignore[assignment]
    DB_AVAILABLE = False


def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


async def get_authenticated_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,  # type: ignore[arg-type]
) -> Subscription:
    """
    Resolve subscription using Excel email first, with API-key fallback.

    Priority:
    1) `X-Excel-User-Email` or `X-User-Email` header (DB lookup)
    2) `email` query parameter (DB lookup)
    3) Legacy `X-API-Key` header / `api_key` query parameter
    """
    request_email = _normalize_email(
        request.headers.get("X-Excel-User-Email")
        or request.headers.get("X-User-Email")
        or request.query_params.get("email")
    )

    if DB_AVAILABLE and db is not None and request_email:
        subscription = await subscription_service.get_subscription_by_email(db, request_email)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"No active subscription found for Excel email '{request_email}'.",
            )

        if not subscription.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription is inactive.")

        if subscription.is_expired:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription has expired.")

        return subscription

    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if api_key:
        subscription = subscription_store.get_subscription(api_key)

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        if not subscription.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key has been revoked.")

        if subscription.is_expired:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription has expired.")

        return subscription

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing API key or Excel user email. Provide X-Excel-User-Email (preferred) or X-API-Key.",
    )


async def enforce_rate_limit(
    request: Request,
    subscription: Subscription = Depends(get_authenticated_subscription),
    db: AsyncSession = Depends(get_db) if DB_AVAILABLE else None,  # type: ignore[arg-type]
) -> Subscription:
    """Rate-limit using DB-backed service when available, else in-memory fallback."""
    if DB_AVAILABLE and db is not None and not subscription.metadata.get("is_dev_key"):
        allowed, error_message = await subscription_service.check_rate_limit(db, subscription)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_message,
                headers={"Retry-After": "60"},
            )

        await subscription_service.record_request(
            db,
            subscription,
            endpoint=request.url.path,
        )
        return subscription

    allowed, error_message = subscription_store.check_rate_limit(subscription)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message,
            headers={"Retry-After": "60"},
        )

    subscription_store.record_request(subscription)
    return subscription
