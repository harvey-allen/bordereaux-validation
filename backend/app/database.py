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


class UserSubscription(Base):
    """
    User subscription stored in PostgreSQL.
    
    Links Excel user accounts (via email) to their subscription tier.
    """
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Excel user identity (from Office.js)
    excel_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # API key (hashed)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # For display: "bx_tri_..."
    
    # Subscription details
    tier: Mapped[str] = mapped_column(
        SQLEnum(SubscriptionTier, name="subscription_tier", create_constraint=True),
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
    # Test type categorisation (LOGIC, QUALITY, MISSING, LOOKUP, etc.)
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
        UniqueConstraint("user_id", "sheet_name", "test_pack", name="uq_pack_config_user_sheet_pack"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
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
            text("ALTER TABLE validation_runs ALTER COLUMN test_packs TYPE TEXT")
        )
        await conn.execute(
            text("ALTER TABLE test_results ALTER COLUMN target_columns TYPE TEXT")
        )



async def close_db() -> None:
    """Close the database connection pool."""
    await engine.dispose()
