#!/usr/bin/env python3
"""Create or update a user subscription in PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.auth import SubscriptionTier
from app.database import Organisation, UserSubscription, async_session_maker
from app.subscription_service import generate_api_key, hash_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add or update a user subscription.")
    parser.add_argument("--email", required=True, help="User email address.")
    parser.add_argument("--excel-user-id", help="Excel user ID. If omitted, generated from email.")
    parser.add_argument("--display-name", default=None, help="Display name for the user.")
    parser.add_argument(
        "--tier",
        choices=[tier.value for tier in SubscriptionTier],
        default=SubscriptionTier.BORDEREAUX.value,
        help="Subscription tier.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create/update user as inactive.",
    )
    parser.add_argument(
        "--regenerate-api-key",
        action="store_true",
        help="Regenerate API key if user already exists.",
    )
    parser.add_argument(
        "--organisation",
        default=None,
        help="Organisation name (defaults to email domain).",
    )
    return parser.parse_args()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def default_excel_user_id(email: str) -> str:
    normalized = normalize_email(email)
    return f"excel_{normalized.replace('@', '_at_').replace('.', '_')}"


async def add_or_update_user(args: argparse.Namespace) -> None:
    email = normalize_email(args.email)
    excel_user_id = (args.excel_user_id or default_excel_user_id(email)).strip()
    tier = SubscriptionTier(args.tier)
    is_active = not args.inactive
    organisation_name = (args.organisation or email.split("@")[-1] or "default").strip().lower()

    async with async_session_maker() as session:
        result = await session.execute(
            select(UserSubscription).where(UserSubscription.excel_user_id == excel_user_id)
        )
        user = result.scalar_one_or_none()

        org_result = await session.execute(
            select(Organisation).where(func.lower(Organisation.name) == organisation_name)
        )
        organisation = org_result.scalar_one_or_none()
        if organisation is None:
            organisation = Organisation(name=organisation_name, created_at=datetime.now(timezone.utc))
            session.add(organisation)
            await session.flush()

        if user is None:
            result = await session.execute(
                select(UserSubscription)
                .where(func.lower(UserSubscription.email) == email)
                .order_by(UserSubscription.created_at.desc())
            )
            user = result.scalars().first()

        issued_api_key: str | None = None

        if user is None:
            issued_api_key = generate_api_key(tier)
            user = UserSubscription(
                organisation_id=int(organisation.id),
                excel_user_id=excel_user_id,
                email=email,
                display_name=args.display_name,
                api_key_hash=hash_api_key(issued_api_key),
                api_key_prefix=issued_api_key[:12] + "...",
                tier=tier,
                is_active=is_active,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user)
            action = "created"
        else:
            user.organisation_id = int(organisation.id)
            user.email = email
            user.excel_user_id = excel_user_id
            user.display_name = args.display_name if args.display_name is not None else user.display_name
            user.tier = tier
            user.is_active = is_active

            if args.regenerate_api_key:
                issued_api_key = generate_api_key(tier)
                user.api_key_hash = hash_api_key(issued_api_key)
                user.api_key_prefix = issued_api_key[:12] + "..."

            action = "updated"

        await session.commit()
        await session.refresh(user)

    print(f"User {action} successfully.")
    print(f"id={user.id}")
    print(f"email={user.email}")
    print(f"excel_user_id={user.excel_user_id}")
    print(f"organisation={organisation_name}")
    print(f"tier={user.tier}")
    print(f"active={user.is_active}")
    print(f"api_key_prefix={user.api_key_prefix}")

    if issued_api_key:
        print("\nIssued API key (shown only now):")
        print(issued_api_key)


async def main() -> None:
    args = parse_args()
    await add_or_update_user(args)


if __name__ == "__main__":
    asyncio.run(main())
