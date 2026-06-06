"""
Database configuration and models for PostgreSQL.

Uses SQLAlchemy with asyncpg for async database access.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, JSON, UniqueConstraint, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.auth import SubscriptionTier

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()


# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bordereaux")

# Convert to async URL if needed
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL


# SQLAlchemy async engine
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_size=5,
    max_overflow=10,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Organisation(Base):
    """Organisation boundary for users and workbook/sheet contexts."""
    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SheetKey(Base):
    """Core unique key for organisation + workbook + sheet + test_pack."""
    __tablename__ = "sheet_keys"
    __table_args__ = (
        UniqueConstraint("organisation_id", "workbook_name", "sheet_name", "test_pack", name="uq_sheet_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workbook_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_pack: Mapped[str] = mapped_column(String(255), nullable=False, default="__unknown_pack__")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UserSubscription(Base):
    """
    User subscription stored in PostgreSQL.
    
    Links Excel user accounts (via email) to their subscription tier.
    """
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    
    # Excel user identity (from Office.js)
    excel_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # API key (hashed)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # For display: "bx_tri_..."
    
    # Subscription details
    tier: Mapped[str] = mapped_column(
        SQLEnum(
            SubscriptionTier,
            name="subscription_tier",
            create_constraint=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=SubscriptionTier.BORDEREAUX,
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Extra data (JSON-like text field for flexibility)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<UserSubscription(email={self.email}, tier={self.tier}, active={self.is_active})>"


class RequestLog(Base):
    """
    Request logging for rate limiting and analytics.
    
    Stores recent requests for rate limit checking.
    """
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(String(100), nullable=True)
    cell_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ValidationRun(Base):
    """One row per validation run, keyed by sheet_key and run timestamp."""
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_token: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    run_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    workbook_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    range_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    test_packs: Mapped[str] = mapped_column(Text, nullable=False)  # comma-separated

    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Per-pack/test breakdown stored as the coverage report packs dict
    coverage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tagged_cells_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<ValidationRun(run={self.run_token}, packs={self.test_packs})>"


class PackConfiguration(Base):
    """Persisted per-user test pack configuration by sheet."""
    __tablename__ = "pack_configurations"
    __table_args__ = (
        UniqueConstraint("user_id", "sheet_key_id", "test_pack", name="uq_pack_config_user_context_pack"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    test_pack: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    workbook_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ValidationResultVersion(Base):
    """Single latest saved result per sheet_key + test_pack."""
    __tablename__ = "validation_result_versions"
    __table_args__ = (
        UniqueConstraint("sheet_key_id", "test_pack", name="uq_result_version_per_sheet_pack"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    test_pack: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tagged_cells_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ValidationResultPayload(Base):
    """Mapped headers and saved row payload for each saved result version."""
    __tablename__ = "validation_result_payloads"
    __table_args__ = (
        UniqueConstraint("validation_result_version_id", name="uq_result_payload_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_result_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("validation_result_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mapped_headers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    saved_data_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ExceptionStatus(str, Enum):
    """Status options for exceptions."""
    TODO = "to do"
    IN_PROGRESS = "in progress"
    IN_REVIEW = "in review"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class Exception(Base):
    """
    Exception management at organisation level.
    
    Allows users to define and apply exceptions to validation issues,
    linked to specific test IDs (optional).
    """
    __tablename__ = "exceptions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "exception_id", name="uq_exception_per_org"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # User-defined exception ID (must be unique within organisation)
    exception_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Optional linked test ID (from rules engine)
    test_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    # Exception details
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[str] = mapped_column(
        SQLEnum(
            ExceptionStatus,
            name="exception_status",
            create_constraint=True,
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=ExceptionStatus.TODO,
    )
    
    # User who created the exception
    author_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Exception(org={self.organisation_id}, id={self.exception_id}, status={self.status})>"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize tables and rebuild result/run persistence schema."""
    async with engine.begin() as conn:
        # Drop old per-test table and old validation_runs schema; recreate as one-row-per-run.
        await conn.execute(text("DROP TABLE IF EXISTS test_results CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS validation_runs CASCADE"))

        # Create baseline ORM schema before applying migration tweaks.
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(
            text(
                """
                ALTER TABLE validation_runs
                ADD COLUMN IF NOT EXISTS tagged_cells_json JSON NOT NULL DEFAULT '[]'::json
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE validation_result_versions
                ADD COLUMN IF NOT EXISTS tagged_cells_json JSON NOT NULL DEFAULT '[]'::json
                """
            )
        )

        # Keep saved result versions, and move payload to dedicated table if legacy columns exist.
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS validation_result_payloads (
                    id SERIAL PRIMARY KEY,
                    validation_result_version_id INTEGER NOT NULL UNIQUE REFERENCES validation_result_versions(id) ON DELETE CASCADE,
                    mapped_headers_json JSON NOT NULL DEFAULT '{}'::json,
                    saved_data_json JSON NOT NULL DEFAULT '[]'::json,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        tagged_cells_payload_col = await conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='validation_result_payloads' AND column_name='tagged_cells_json'
                LIMIT 1
                """
            )
        )
        if tagged_cells_payload_col.scalar() is not None:
            await conn.execute(
                text(
                    """
                    UPDATE validation_result_versions v
                    SET tagged_cells_json = COALESCE(p.tagged_cells_json, '[]'::json)
                    FROM validation_result_payloads p
                    WHERE p.validation_result_version_id = v.id
                      AND COALESCE(v.tagged_cells_json, '[]'::json) = '[]'::json
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE validation_result_payloads
                    DROP COLUMN IF EXISTS tagged_cells_json
                    """
                )
            )
        legacy_payload_col = await conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name='validation_result_versions' AND column_name='mapped_headers_json'
                LIMIT 1
                """
            )
        )
        if legacy_payload_col.scalar() is not None:
            await conn.execute(
                text(
                    """
                    INSERT INTO validation_result_payloads (validation_result_version_id, mapped_headers_json, saved_data_json, created_at, updated_at)
                    SELECT v.id,
                           COALESCE(v.mapped_headers_json, '{}'::json),
                           COALESCE(v.saved_data_json, '[]'::json),
                           COALESCE(v.created_at, NOW()),
                           COALESCE(v.updated_at, NOW())
                    FROM validation_result_versions v
                    ON CONFLICT (validation_result_version_id) DO NOTHING
                    """
                )
            )
            await conn.execute(text("ALTER TABLE validation_result_versions DROP COLUMN IF EXISTS mapped_headers_json"))
            await conn.execute(text("ALTER TABLE validation_result_versions DROP COLUMN IF EXISTS saved_data_json"))

        # Ensure sheet key semantics include pack key.
        await conn.execute(text("ALTER TABLE sheet_keys ALTER COLUMN test_pack SET DEFAULT '__unknown_pack__'"))
        await conn.execute(text("UPDATE sheet_keys SET test_pack='__unknown_pack__' WHERE test_pack IS NULL OR btrim(test_pack) = ''"))
        await conn.execute(text("ALTER TABLE sheet_keys ALTER COLUMN test_pack SET NOT NULL"))
        await conn.execute(text("ALTER TABLE sheet_keys DROP CONSTRAINT IF EXISTS uq_sheet_key"))
        await conn.execute(
            text(
                """
                ALTER TABLE sheet_keys
                ADD CONSTRAINT uq_sheet_key UNIQUE (organisation_id, workbook_name, sheet_name, test_pack)
                """
            )
        )

        # Ensure saved result keying is per sheet_key + pack.
        await conn.execute(text("ALTER TABLE validation_result_versions ADD COLUMN IF NOT EXISTS test_pack VARCHAR(100)"))
        await conn.execute(text("UPDATE validation_result_versions SET test_pack='__unknown_pack__' WHERE test_pack IS NULL OR btrim(test_pack) = ''"))
        await conn.execute(text("ALTER TABLE validation_result_versions ALTER COLUMN test_pack SET NOT NULL"))
        await conn.execute(text("ALTER TABLE validation_result_versions DROP CONSTRAINT IF EXISTS uq_result_version_per_sheet"))
        await conn.execute(text("ALTER TABLE validation_result_versions DROP CONSTRAINT IF EXISTS validation_result_versions_sheet_key_id_key"))
        await conn.execute(text("ALTER TABLE validation_result_versions DROP CONSTRAINT IF EXISTS uq_result_version_per_sheet_pack"))
        await conn.execute(text("ALTER TABLE validation_result_versions ADD CONSTRAINT uq_result_version_per_sheet_pack UNIQUE (sheet_key_id, test_pack)"))

        # Seed default organisation if absent.
        await conn.execute(
            text(
                """
                INSERT INTO organisations (name, created_at)
                SELECT 'default', NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM organisations WHERE name = 'default'
                )
                """
            )
        )

async def close_db() -> None:
    """Close the database connection pool."""
    await engine.dispose()
