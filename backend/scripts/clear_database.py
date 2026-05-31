#!/usr/bin/env python3
"""Clear rows from PostgreSQL tables (keeps schema).

Examples
--------
Clear everything:
    python clear_database.py --yes

Clear a specific table:
    python clear_database.py --table validation_runs --yes

Clear multiple tables:
    python clear_database.py --table validation_runs --table test_results --yes
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.database import Base, engine


KNOWN_TABLES = [table.name for table in Base.metadata.sorted_tables]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear rows from PostgreSQL tables (keeps schema).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Known tables:\n" + "\n".join(f"  {t}" for t in KNOWN_TABLES),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    parser.add_argument(
        "--table",
        dest="tables",
        action="append",
        metavar="TABLE",
        help="Target a specific table. Can be repeated. Defaults to all tables.",
    )
    return parser.parse_args()


async def clear_tables(table_names: list[str]) -> None:
    if not table_names:
        print("No tables to clear.")
        return

    quoted = ", ".join(f'"{name}"' for name in table_names)
    truncate_sql = text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")

    async with engine.begin() as conn:
        await conn.execute(truncate_sql)

    print("Done. Tables truncated:")
    for name in table_names:
        print(f"  - {name}")


async def main() -> None:
    args = parse_args()

    # Resolve target tables
    if args.tables:
        invalid = [t for t in args.tables if t not in KNOWN_TABLES]
        if invalid:
            print(f"Error: unknown table(s): {', '.join(invalid)}")
            print(f"Known tables: {', '.join(KNOWN_TABLES)}")
            raise SystemExit(1)
        target_tables = args.tables
        scope = f"table(s): {', '.join(target_tables)}"
    else:
        target_tables = KNOWN_TABLES
        scope = "ALL tables"

    if not args.yes:
        answer = input(f"This will delete all data from {scope}. Continue? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return

    await clear_tables(target_tables)


if __name__ == "__main__":
    asyncio.run(main())
