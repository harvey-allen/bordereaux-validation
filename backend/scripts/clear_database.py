#!/usr/bin/env python3
"""Clear all application data from PostgreSQL tables (keeps schema)."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.database import Base, engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear all rows from database tables.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    return parser.parse_args()


async def clear_database() -> None:
    table_names = [table.name for table in Base.metadata.sorted_tables]
    if not table_names:
        print("No tables found in metadata. Nothing to clear.")
        return

    quoted = ", ".join(f'"{name}"' for name in table_names)
    truncate_sql = text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")

    async with engine.begin() as conn:
        await conn.execute(truncate_sql)

    print("Database cleared successfully.")
    print("Tables truncated:")
    for name in table_names:
        print(f"- {name}")


async def main() -> None:
    args = parse_args()

    if not args.yes:
        answer = input("This will delete ALL data from all tables. Continue? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return

    await clear_database()


if __name__ == "__main__":
    asyncio.run(main())
