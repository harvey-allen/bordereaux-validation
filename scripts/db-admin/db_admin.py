#!/usr/bin/env python3
"""
Database administration utilities for managing users and organisations.

Provides CRUD operations for UserSubscription and Organisation models.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import secrets
import sys
from datetime import datetime, timezone
from typing import Optional

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))

from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from app.database import (
    async_session_maker,
    Organisation,
    UserSubscription,
    engine,
)
from app.auth import SubscriptionTier


# ─────────────────────────────────────────────────────────────────────────────
# Organisation CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def list_organisations(name_filter: Optional[str] = None) -> None:
    """List all organisations, optionally filtered by name."""
    async with async_session_maker() as session:
        stmt = select(Organisation).order_by(Organisation.id)
        if name_filter:
            stmt = stmt.where(Organisation.name.ilike(f"%{name_filter}%"))
        result = await session.execute(stmt)
        orgs = result.scalars().all()

        if not orgs:
            print("No organisations found.")
            return

        print(f"{'ID':<6} {'Name':<40} {'Created At':<25}")
        print("-" * 75)
        for org in orgs:
            created = org.created_at.strftime("%Y-%m-%d %H:%M:%S") if org.created_at else "N/A"
            print(f"{org.id:<6} {org.name:<40} {created:<25}")
        print(f"\nTotal: {len(orgs)} organisation(s)")


async def get_organisation(org_id: Optional[int] = None, name: Optional[str] = None) -> None:
    """Get details of a specific organisation by ID or name."""
    async with async_session_maker() as session:
        if org_id:
            stmt = select(Organisation).where(Organisation.id == org_id)
        elif name:
            stmt = select(Organisation).where(Organisation.name == name)
        else:
            print("Error: Must provide either --id or --name")
            sys.exit(1)

        result = await session.execute(stmt)
        org = result.scalar_one_or_none()

        if not org:
            print("Organisation not found.")
            sys.exit(1)

        print(f"Organisation Details:")
        print(f"  ID:         {org.id}")
        print(f"  Name:       {org.name}")
        print(f"  Created At: {org.created_at}")

        # Count users in this organisation
        user_stmt = select(UserSubscription).where(UserSubscription.organisation_id == org.id)
        user_result = await session.execute(user_stmt)
        users = user_result.scalars().all()
        print(f"  Users:      {len(users)}")


async def create_organisation(name: str) -> None:
    """Create a new organisation."""
    async with async_session_maker() as session:
        org = Organisation(name=name)
        session.add(org)
        try:
            await session.commit()
            await session.refresh(org)
            print(f"Organisation created successfully:")
            print(f"  ID:   {org.id}")
            print(f"  Name: {org.name}")
        except IntegrityError:
            await session.rollback()
            print(f"Error: Organisation with name '{name}' already exists.")
            sys.exit(1)


async def update_organisation(org_id: int, new_name: str) -> None:
    """Update an organisation's name."""
    async with async_session_maker() as session:
        stmt = select(Organisation).where(Organisation.id == org_id)
        result = await session.execute(stmt)
        org = result.scalar_one_or_none()

        if not org:
            print(f"Error: Organisation with ID {org_id} not found.")
            sys.exit(1)

        old_name = org.name
        org.name = new_name
        try:
            await session.commit()
            print(f"Organisation updated successfully:")
            print(f"  ID:       {org.id}")
            print(f"  Old Name: {old_name}")
            print(f"  New Name: {org.name}")
        except IntegrityError:
            await session.rollback()
            print(f"Error: Organisation with name '{new_name}' already exists.")
            sys.exit(1)


async def delete_organisation(org_id: int, force: bool = False) -> None:
    """Delete an organisation."""
    async with async_session_maker() as session:
        stmt = select(Organisation).where(Organisation.id == org_id)
        result = await session.execute(stmt)
        org = result.scalar_one_or_none()

        if not org:
            print(f"Error: Organisation with ID {org_id} not found.")
            sys.exit(1)

        # Check for associated users
        user_stmt = select(UserSubscription).where(UserSubscription.organisation_id == org_id)
        user_result = await session.execute(user_stmt)
        users = user_result.scalars().all()

        if users and not force:
            print(f"Error: Organisation has {len(users)} associated user(s).")
            print("Use --force to delete anyway (users will be orphaned or fail due to FK).")
            sys.exit(1)

        await session.delete(org)
        try:
            await session.commit()
            print(f"Organisation '{org.name}' (ID: {org_id}) deleted successfully.")
        except IntegrityError as e:
            await session.rollback()
            print(f"Error: Cannot delete organisation due to existing references.")
            print(f"Details: {e}")
            sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# User CRUD
# ─────────────────────────────────────────────────────────────────────────────


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key, returning (raw_key, key_hash, key_prefix)."""
    raw_key = f"bx_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12] + "..."
    return raw_key, key_hash, key_prefix


async def list_users(
    org_id: Optional[int] = None,
    tier: Optional[str] = None,
    active_only: bool = False,
    inactive_only: bool = False,
) -> None:
    """List all users with optional filters."""
    async with async_session_maker() as session:
        stmt = select(UserSubscription, Organisation.name).join(
            Organisation, UserSubscription.organisation_id == Organisation.id
        ).order_by(UserSubscription.id)

        if org_id:
            stmt = stmt.where(UserSubscription.organisation_id == org_id)
        if tier:
            stmt = stmt.where(UserSubscription.tier == tier)
        if active_only:
            stmt = stmt.where(UserSubscription.is_active == True)
        if inactive_only:
            stmt = stmt.where(UserSubscription.is_active == False)

        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            print("No users found.")
            return

        print(f"{'ID':<6} {'Email':<35} {'Org':<20} {'Tier':<12} {'Active':<8} {'API Key Prefix':<15}")
        print("-" * 100)
        for user, org_name in rows:
            active_str = "Yes" if user.is_active else "No"
            print(f"{user.id:<6} {user.email:<35} {org_name:<20} {user.tier:<12} {active_str:<8} {user.api_key_prefix:<15}")
        print(f"\nTotal: {len(rows)} user(s)")


async def get_user(
    user_id: Optional[int] = None,
    email: Optional[str] = None,
    excel_user_id: Optional[str] = None,
) -> None:
    """Get details of a specific user."""
    async with async_session_maker() as session:
        stmt = select(UserSubscription, Organisation.name).join(
            Organisation, UserSubscription.organisation_id == Organisation.id
        )

        if user_id:
            stmt = stmt.where(UserSubscription.id == user_id)
        elif email:
            stmt = stmt.where(UserSubscription.email == email)
        elif excel_user_id:
            stmt = stmt.where(UserSubscription.excel_user_id == excel_user_id)
        else:
            print("Error: Must provide --id, --email, or --excel-user-id")
            sys.exit(1)

        result = await session.execute(stmt)
        row = result.one_or_none()

        if not row:
            print("User not found.")
            sys.exit(1)

        user, org_name = row
        print(f"User Details:")
        print(f"  ID:            {user.id}")
        print(f"  Email:         {user.email}")
        print(f"  Display Name:  {user.display_name or 'N/A'}")
        print(f"  Excel User ID: {user.excel_user_id}")
        print(f"  Organisation:  {org_name} (ID: {user.organisation_id})")
        print(f"  Tier:          {user.tier}")
        print(f"  Active:        {user.is_active}")
        print(f"  API Key:       {user.api_key_prefix}")
        print(f"  Created At:    {user.created_at}")
        print(f"  Expires At:    {user.expires_at or 'Never'}")
        print(f"  Last Used:     {user.last_used_at or 'Never'}")


async def create_user(
    email: str,
    organisation_id: int,
    excel_user_id: Optional[str] = None,
    display_name: Optional[str] = None,
    tier: str = "bordereaux",
) -> None:
    """Create a new user with a generated API key."""
    # Generate Excel user ID if not provided
    if not excel_user_id:
        excel_user_id = f"excel_{secrets.token_urlsafe(16)}"

    raw_key, key_hash, key_prefix = generate_api_key()

    async with async_session_maker() as session:
        # Verify organisation exists
        org_stmt = select(Organisation).where(Organisation.id == organisation_id)
        org_result = await session.execute(org_stmt)
        org = org_result.scalar_one_or_none()

        if not org:
            print(f"Error: Organisation with ID {organisation_id} not found.")
            sys.exit(1)

        # Coerce tier value
        try:
            tier_enum = SubscriptionTier(tier.lower())
        except ValueError:
            print(f"Error: Invalid tier '{tier}'. Valid tiers: {[t.value for t in SubscriptionTier]}")
            sys.exit(1)

        user = UserSubscription(
            email=email,
            organisation_id=organisation_id,
            excel_user_id=excel_user_id,
            display_name=display_name,
            tier=tier_enum,
            api_key_hash=key_hash,
            api_key_prefix=key_prefix,
            is_active=True,
        )
        session.add(user)

        try:
            await session.commit()
            await session.refresh(user)
            print(f"User created successfully:")
            print(f"  ID:            {user.id}")
            print(f"  Email:         {user.email}")
            print(f"  Organisation:  {org.name} (ID: {org.id})")
            print(f"  Tier:          {user.tier}")
            print(f"  Excel User ID: {user.excel_user_id}")
            print()
            print(f"  *** API KEY (save this - shown only once): ***")
            print(f"  {raw_key}")
            print()
        except IntegrityError as e:
            await session.rollback()
            if "excel_user_id" in str(e):
                print(f"Error: User with Excel User ID '{excel_user_id}' already exists.")
            elif "email" in str(e):
                print(f"Error: User with email '{email}' may already exist.")
            else:
                print(f"Error: {e}")
            sys.exit(1)


async def update_user(
    user_id: int,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    organisation_id: Optional[int] = None,
    tier: Optional[str] = None,
    active: Optional[bool] = None,
) -> None:
    """Update a user's details."""
    async with async_session_maker() as session:
        stmt = select(UserSubscription).where(UserSubscription.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with ID {user_id} not found.")
            sys.exit(1)

        changes = []
        if email is not None:
            changes.append(f"email: {user.email} -> {email}")
            user.email = email
        if display_name is not None:
            changes.append(f"display_name: {user.display_name} -> {display_name}")
            user.display_name = display_name
        if organisation_id is not None:
            # Verify new org exists
            org_stmt = select(Organisation).where(Organisation.id == organisation_id)
            org_result = await session.execute(org_stmt)
            org = org_result.scalar_one_or_none()
            if not org:
                print(f"Error: Organisation with ID {organisation_id} not found.")
                sys.exit(1)
            changes.append(f"organisation_id: {user.organisation_id} -> {organisation_id}")
            user.organisation_id = organisation_id
        if tier is not None:
            try:
                tier_enum = SubscriptionTier(tier.lower())
            except ValueError:
                print(f"Error: Invalid tier '{tier}'. Valid tiers: {[t.value for t in SubscriptionTier]}")
                sys.exit(1)
            changes.append(f"tier: {user.tier} -> {tier_enum.value}")
            user.tier = tier_enum
        if active is not None:
            changes.append(f"is_active: {user.is_active} -> {active}")
            user.is_active = active

        if not changes:
            print("No changes specified.")
            return

        try:
            await session.commit()
            print(f"User {user_id} updated successfully:")
            for change in changes:
                print(f"  {change}")
        except IntegrityError as e:
            await session.rollback()
            print(f"Error: {e}")
            sys.exit(1)


async def regenerate_api_key(user_id: int) -> None:
    """Regenerate API key for a user."""
    raw_key, key_hash, key_prefix = generate_api_key()

    async with async_session_maker() as session:
        stmt = select(UserSubscription).where(UserSubscription.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with ID {user_id} not found.")
            sys.exit(1)

        old_prefix = user.api_key_prefix
        user.api_key_hash = key_hash
        user.api_key_prefix = key_prefix

        await session.commit()
        print(f"API key regenerated for user {user_id} ({user.email}):")
        print(f"  Old Prefix: {old_prefix}")
        print(f"  New Prefix: {key_prefix}")
        print()
        print(f"  *** NEW API KEY (save this - shown only once): ***")
        print(f"  {raw_key}")
        print()


async def delete_user(user_id: int, force: bool = False) -> None:
    """Delete a user."""
    async with async_session_maker() as session:
        stmt = select(UserSubscription).where(UserSubscription.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with ID {user_id} not found.")
            sys.exit(1)

        if not force:
            print(f"Warning: This will delete user '{user.email}' (ID: {user_id}).")
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() != "yes":
                print("Cancelled.")
                return

        email = user.email
        await session.delete(user)
        await session.commit()
        print(f"User '{email}' (ID: {user_id}) deleted successfully.")


async def deactivate_user(user_id: int) -> None:
    """Deactivate a user (soft delete)."""
    await update_user(user_id, active=False)


async def activate_user(user_id: int) -> None:
    """Activate a user."""
    await update_user(user_id, active=True)


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Points
# ─────────────────────────────────────────────────────────────────────────────


def org_cli(args: argparse.Namespace) -> None:
    """Handle organisation commands."""
    if args.org_action == "list":
        asyncio.run(list_organisations(args.filter))
    elif args.org_action == "get":
        asyncio.run(get_organisation(org_id=args.id, name=args.name))
    elif args.org_action == "create":
        asyncio.run(create_organisation(args.name))
    elif args.org_action == "update":
        asyncio.run(update_organisation(args.id, args.name))
    elif args.org_action == "delete":
        asyncio.run(delete_organisation(args.id, force=args.force))


def user_cli(args: argparse.Namespace) -> None:
    """Handle user commands."""
    if args.user_action == "list":
        asyncio.run(list_users(
            org_id=args.org_id,
            tier=args.tier,
            active_only=args.active,
            inactive_only=args.inactive,
        ))
    elif args.user_action == "get":
        asyncio.run(get_user(
            user_id=args.id,
            email=args.email,
            excel_user_id=args.excel_user_id,
        ))
    elif args.user_action == "create":
        asyncio.run(create_user(
            email=args.email,
            organisation_id=args.org_id,
            excel_user_id=args.excel_user_id,
            display_name=args.display_name,
            tier=args.tier,
        ))
    elif args.user_action == "update":
        asyncio.run(update_user(
            user_id=args.id,
            email=args.email,
            display_name=args.display_name,
            organisation_id=args.org_id,
            tier=args.tier,
            active=args.active,
        ))
    elif args.user_action == "delete":
        asyncio.run(delete_user(args.id, force=args.force))
    elif args.user_action == "activate":
        asyncio.run(activate_user(args.id))
    elif args.user_action == "deactivate":
        asyncio.run(deactivate_user(args.id))
    elif args.user_action == "regenerate-key":
        asyncio.run(regenerate_api_key(args.id))


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Database administration for users and organisations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ─── Organisation commands ───────────────────────────────────────────────
    org_parser = subparsers.add_parser("org", help="Organisation management")
    org_subparsers = org_parser.add_subparsers(dest="org_action", required=True)

    # org list
    org_list = org_subparsers.add_parser("list", help="List organisations")
    org_list.add_argument("--filter", "-f", help="Filter by name (partial match)")

    # org get
    org_get = org_subparsers.add_parser("get", help="Get organisation details")
    org_get.add_argument("--id", type=int, help="Organisation ID")
    org_get.add_argument("--name", "-n", help="Organisation name")

    # org create
    org_create = org_subparsers.add_parser("create", help="Create organisation")
    org_create.add_argument("--name", "-n", required=True, help="Organisation name")

    # org update
    org_update = org_subparsers.add_parser("update", help="Update organisation")
    org_update.add_argument("--id", type=int, required=True, help="Organisation ID")
    org_update.add_argument("--name", "-n", required=True, help="New name")

    # org delete
    org_delete = org_subparsers.add_parser("delete", help="Delete organisation")
    org_delete.add_argument("--id", type=int, required=True, help="Organisation ID")
    org_delete.add_argument("--force", "-f", action="store_true", help="Force delete")

    org_parser.set_defaults(func=org_cli)

    # ─── User commands ───────────────────────────────────────────────────────
    user_parser = subparsers.add_parser("user", help="User management")
    user_subparsers = user_parser.add_subparsers(dest="user_action", required=True)

    # user list
    user_list = user_subparsers.add_parser("list", help="List users")
    user_list.add_argument("--org-id", type=int, help="Filter by organisation ID")
    user_list.add_argument("--tier", help="Filter by subscription tier")
    user_list.add_argument("--active", action="store_true", help="Show active users only")
    user_list.add_argument("--inactive", action="store_true", help="Show inactive users only")

    # user get
    user_get = user_subparsers.add_parser("get", help="Get user details")
    user_get.add_argument("--id", type=int, help="User ID")
    user_get.add_argument("--email", "-e", help="User email")
    user_get.add_argument("--excel-user-id", help="Excel user ID")

    # user create
    user_create = user_subparsers.add_parser("create", help="Create user")
    user_create.add_argument("--email", "-e", required=True, help="User email")
    user_create.add_argument("--org-id", type=int, required=True, help="Organisation ID")
    user_create.add_argument("--excel-user-id", help="Excel user ID (auto-generated if not provided)")
    user_create.add_argument("--display-name", "-d", help="Display name")
    user_create.add_argument("--tier", "-t", default="bordereaux", help="Subscription tier (default: bordereaux)")

    # user update
    user_update = user_subparsers.add_parser("update", help="Update user")
    user_update.add_argument("--id", type=int, required=True, help="User ID")
    user_update.add_argument("--email", "-e", help="New email")
    user_update.add_argument("--display-name", "-d", help="New display name")
    user_update.add_argument("--org-id", type=int, help="New organisation ID")
    user_update.add_argument("--tier", "-t", help="New subscription tier")
    user_update.add_argument("--active", type=lambda x: x.lower() == "true", help="Set active status (true/false)")

    # user delete
    user_delete = user_subparsers.add_parser("delete", help="Delete user")
    user_delete.add_argument("--id", type=int, required=True, help="User ID")
    user_delete.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # user activate
    user_activate = user_subparsers.add_parser("activate", help="Activate user")
    user_activate.add_argument("--id", type=int, required=True, help="User ID")

    # user deactivate
    user_deactivate = user_subparsers.add_parser("deactivate", help="Deactivate user")
    user_deactivate.add_argument("--id", type=int, required=True, help="User ID")

    # user regenerate-key
    user_regen = user_subparsers.add_parser("regenerate-key", help="Regenerate API key")
    user_regen.add_argument("--id", type=int, required=True, help="User ID")

    user_parser.set_defaults(func=user_cli)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
