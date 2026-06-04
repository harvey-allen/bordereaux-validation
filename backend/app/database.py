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


class SheetKey(Base):
    """Core unique key for organisation + workbook + sheet + test_pack."""
    __tablename__ = "sheet_keys"
    __table_args__ = (
        UniqueConstraint("organisation_id", "workbook_name", "sheet_name", name="uq_sheet_key"),
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
    test_pack: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Updated from last validation
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
    """Single saved result version per sheet_key, stores failed UMRs, passed UMRs, and passed test IDs."""
    __tablename__ = "validation_result_versions"
    __table_args__ = (
        UniqueConstraint("sheet_key_id", name="uq_result_version_per_sheet"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sheet_key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sheet_keys.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # JSON: {
    #   "failed": [
    #     {"id": "UMR1", "tests": ["test_id_1", "test_id_2"]},
    #     ...
    #   ],
    #   "passed_umrs": ["UMR2", "UMR3"],
    #   "passed_tests": ["test_id_1", "test_id_2", ...],
    #   "passed_ids": ["test_id_1", "test_id_2", ...]  (legacy, same as passed_tests)
    # }
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize the database tables. Drop old tables first for clean rebuild."""
    async with engine.begin() as conn:
        # Drop old tables if they exist
        await conn.execute(
            text("DROP TABLE IF EXISTS validation_result_versions CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS pack_configurations CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS organisation_workbook_sheet_keys CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS sheet_keys CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS test_results CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS validation_runs CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS request_logs CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS user_subscriptions CASCADE")
        )
        await conn.execute(
            text("DROP TABLE IF EXISTS organisations CASCADE")
        )

        # Create all tables fresh
        await conn.run_sync(Base.metadata.create_all)

        # Seed default organisation
        await conn.execute(
            text(
                """
                INSERT INTO organisations (name, created_at)
                VALUES ('default', NOW())
                """
            )
        )

        # Ensure subscription_tier enum has all values
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

async def close_db() -> None:
    """Close the database connection pool."""
    await engine.dispose()
