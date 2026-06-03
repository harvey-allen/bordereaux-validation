"""
Database configuration and models for PostgreSQL.

Uses SQLAlchemy with asyncpg for async database access.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, JSON, UniqueConstraint, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


class OrganisationWorkbookSheetKey(Base):
    """Core unique key for organisation + workbook + sheet."""
    __tablename__ = "organisation_workbook_sheet_keys"
    __table_args__ = (
        UniqueConstraint("organisation_id", "workbook_name", "sheet_name", name="uq_org_workbook_sheet"),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
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
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Extra data (JSON-like text field for flexibility)
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    cell_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ValidationRun(Base):
    """
    A validation run - each time a user validates a range.
    
    Stores summary info and links to individual test results.
    """
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Link to user (optional - for anonymous/dev usage)
    user_id: Mapped[int | None] = mapped_column(
        Integer, 
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    api_key_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    
    # Run metadata
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    
    # Workbook/sheet info (if available)
    workbook_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    range_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Test packs used
    test_packs: Mapped[str] = mapped_column(Text, nullable=False)  # Comma-separated
    
    # Summary stats
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_cells: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Overall status
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)  # completed, error, partial
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    test_results: Mapped[list["TestResult"]] = relationship(
        "TestResult",
        back_populates="validation_run",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<ValidationRun(id={self.id}, packs={self.test_packs}, cells={self.total_cells}, failed={self.failed_cells})>"


class TestResult(Base):
    """
    Individual test results from a validation run.
    
    One record per test executed in a validation run.
    """
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Link to validation run
    validation_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("validation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Test identification
    test_pack: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    test_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    test_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Target columns affected by this test
    target_columns: Mapped[str] = mapped_column(Text, nullable=False)  # Comma-separated column names
    
    # Severity level
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # INFO, WARNING, ERROR, CRITICAL
    severity_weight: Mapped[int] = mapped_column(Integer, nullable=False)  # 0, 1, 2, 3
    # Test type categorisation (LOGIC, DATA_TYPE, COMPLETENESS, OTHER, etc.)
    test_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Results
    evaluated_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Failed references (policy IDs, row identifiers, etc.)
    # Stored as JSON array for flexibility
    failed_refs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Relationship back to validation run
    validation_run: Mapped["ValidationRun"] = relationship(
        "ValidationRun",
        back_populates="test_results",
    )
    
    def __repr__(self) -> str:
        return f"<TestResult(test={self.test_pack}.{self.test_name}, passed={self.passed_rows}, failed={self.failed_rows})>"


class PackConfiguration(Base):
    """Persisted per-user test pack configuration by sheet."""
    __tablename__ = "pack_configurations"
    __table_args__ = (
        UniqueConstraint("user_id", "org_workbook_sheet_key_id", "test_pack", name="uq_pack_config_user_context_pack"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_workbook_sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisation_workbook_sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    test_pack: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    workbook_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    """Saved result versions keyed by organisation/workbook/sheet context."""
    __tablename__ = "validation_result_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_workbook_sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisation_workbook_sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize the database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organisations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO organisations (name, created_at)
                VALUES ('default', NOW())
                ON CONFLICT (name) DO NOTHING
                """
            )
        )

        await conn.execute(
            text("ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS organisation_id INTEGER")
        )
        await conn.execute(
            text(
                """
                UPDATE user_subscriptions
                SET organisation_id = (SELECT id FROM organisations WHERE name = 'default')
                WHERE organisation_id IS NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'fk_user_subscriptions_organisation_id'
                    ) THEN
                        ALTER TABLE user_subscriptions
                        ADD CONSTRAINT fk_user_subscriptions_organisation_id
                        FOREIGN KEY (organisation_id)
                        REFERENCES organisations(id)
                        ON DELETE RESTRICT;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(text("ALTER TABLE user_subscriptions ALTER COLUMN organisation_id SET NOT NULL"))

        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organisation_workbook_sheet_keys (
                    id SERIAL PRIMARY KEY,
                    organisation_id INTEGER NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                    workbook_name VARCHAR(255) NOT NULL,
                    sheet_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_org_workbook_sheet UNIQUE (organisation_id, workbook_name, sheet_name)
                )
                """
            )
        )

        await conn.execute(
            text("ALTER TABLE pack_configurations ADD COLUMN IF NOT EXISTS org_workbook_sheet_key_id INTEGER")
        )
        await conn.execute(
            text(
                """
                INSERT INTO organisation_workbook_sheet_keys (organisation_id, workbook_name, sheet_name, created_at)
                SELECT DISTINCT
                    us.organisation_id,
                    COALESCE(NULLIF(pc.workbook_name, ''), '__unknown_workbook__') AS workbook_name,
                    COALESCE(NULLIF(pc.sheet_name, ''), '__unknown_sheet__') AS sheet_name,
                    NOW() AS created_at
                FROM pack_configurations pc
                JOIN user_subscriptions us ON us.id = pc.user_id
                ON CONFLICT (organisation_id, workbook_name, sheet_name) DO NOTHING
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE pack_configurations pc
                SET org_workbook_sheet_key_id = ows.id
                                FROM user_subscriptions us, organisation_workbook_sheet_keys ows
                WHERE pc.user_id = us.id
                                    AND ows.organisation_id = us.organisation_id
                                    AND ows.workbook_name = COALESCE(NULLIF(pc.workbook_name, ''), '__unknown_workbook__')
                                    AND ows.sheet_name = COALESCE(NULLIF(pc.sheet_name, ''), '__unknown_sheet__')
                  AND pc.org_workbook_sheet_key_id IS NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_pack_config_user_sheet_pack'
                    ) THEN
                        ALTER TABLE pack_configurations DROP CONSTRAINT uq_pack_config_user_sheet_pack;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'uq_pack_config_user_context_pack'
                    ) THEN
                        ALTER TABLE pack_configurations
                        ADD CONSTRAINT uq_pack_config_user_context_pack
                        UNIQUE (user_id, org_workbook_sheet_key_id, test_pack);
                    END IF;
                END
                $$;
                """
            )
        )

        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS validation_result_versions (
                    id SERIAL PRIMARY KEY,
                    org_workbook_sheet_key_id INTEGER NOT NULL REFERENCES organisation_workbook_sheet_keys(id) ON DELETE CASCADE,
                    user_id INTEGER NULL REFERENCES user_subscriptions(id) ON DELETE SET NULL,
                    results_json JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subscription_tier') THEN
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'BORDEREAUX';
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'DEVELOPER';
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'TRIAL';
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'bordereaux';
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'developer';
                        ALTER TYPE subscription_tier ADD VALUE IF NOT EXISTS 'trial';
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            text("ALTER TABLE validation_runs ALTER COLUMN test_packs TYPE TEXT")
        )
        await conn.execute(
            text("ALTER TABLE test_results ALTER COLUMN target_columns TYPE TEXT")
        )



async def close_db() -> None:
    """Close the database connection pool."""
    await engine.dispose()
