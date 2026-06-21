"""
Environment-based configuration management.

Handles loading environment-specific settings, database configurations,
AWS credentials, and service initialization based on ENVIRONMENT variable.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class Environment(str, Enum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Config:
    """Base configuration class with environment detection."""

    def __init__(self) -> None:
        """Initialize configuration by loading appropriate .env file."""
        self.environment = self._detect_environment()
        self._load_env_file()
        self._validate_required_vars()

    def _detect_environment(self) -> Environment:
        """Detect environment from ENVIRONMENT variable or default to development."""
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            return Environment(env_str)
        except ValueError:
            print(f"Warning: Invalid ENVIRONMENT={env_str}, defaulting to development")
            return Environment.DEVELOPMENT

    def _load_env_file(self) -> None:
        """Load environment-specific .env file from backend directory."""
        backend_dir = Path(__file__).parent.parent
        env_file = backend_dir / f".env.{self.environment.value}"

        # Always try to load the environment-specific file
        if env_file.exists():
            load_dotenv(env_file, override=True)
        elif self.environment != Environment.DEVELOPMENT:
            print(f"Warning: {env_file} not found, using environment variables only")

        # Also load .env (if exists) as a base, then override with environment-specific
        base_env = backend_dir / ".env"
        if base_env.exists():
            load_dotenv(base_env, override=False)

    def _validate_required_vars(self) -> None:
        """Validate that required environment variables are set."""
        required_vars = ["DATABASE_URL"]

        # S3 is required for production/staging, optional for development
        if self.environment in (Environment.STAGING, Environment.PRODUCTION):
            required_vars.extend(["AWS_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"])

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")

    # Database Configuration
    @property
    def database_url(self) -> str:
        """Get database URL (supports local PostgreSQL or RDS)."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/bordereaux?schema=public",
        )

    @property
    def database_pool_size(self) -> int:
        """Get database connection pool size."""
        return int(os.getenv("DATABASE_POOL_SIZE", "5"))

    @property
    def database_max_overflow(self) -> int:
        """Get database connection pool max overflow."""
        return int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))

    @property
    def sql_echo(self) -> bool:
        """Get SQL echo setting for debugging."""
        return os.getenv("SQL_ECHO", "false").lower() == "true"

    # AWS/S3 Configuration
    @property
    def aws_access_key(self) -> str | None:
        """Get AWS access key."""
        return os.getenv("AWS_ACCESS_KEY")

    @property
    def aws_secret_access_key(self) -> str | None:
        """Get AWS secret access key."""
        return os.getenv("AWS_SECRET_ACCESS_KEY")

    @property
    def aws_region(self) -> str:
        """Get AWS region."""
        return os.getenv("AWS_REGION", "eu-west-2")

    @property
    def report_storage_bucket(self) -> str:
        """Get S3 bucket name for report storage."""
        return os.getenv("REPORT_STORAGE_BUCKET", "bordereaux-report")

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 storage is enabled (disabled in development by default)."""
        if self.environment == Environment.DEVELOPMENT:
            return os.getenv("ENABLE_S3_DEVELOPMENT", "false").lower() == "true"
        return True

    # Subscription & API Configuration
    @property
    def default_subscription_tier(self) -> str:
        """Get default subscription tier for new users."""
        return os.getenv("DEFAULT_SUBSCRIPTION_TIER", "bordereaux")

    @property
    def admin_emails(self) -> list[str]:
        """Get list of admin email addresses."""
        emails_str = os.getenv("ADMIN_EMAILS", "")
        return [email.strip() for email in emails_str.split(",") if email.strip()]

    @property
    def dev_api_key(self) -> str:
        """Get development API key (used for testing and fallback)."""
        return os.getenv("DEV_API_KEY", "dev_bordereaux_key_12345")

    # Environment Checks
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_staging(self) -> bool:
        """Check if running in staging mode."""
        return self.environment == Environment.STAGING

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_local_db(self) -> bool:
        """Check if using local PostgreSQL (development only)."""
        return self.is_development and "localhost" in self.database_url

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary (excluding sensitive data)."""
        return {
            "environment": self.environment.value,
            "database_url": self.database_url.split("@")[0] + "@[REDACTED]",  # Hide credentials
            "database_pool_size": self.database_pool_size,
            "sql_echo": self.sql_echo,
            "s3_enabled": self.s3_enabled,
            "aws_region": self.aws_region,
            "report_storage_bucket": self.report_storage_bucket,
            "default_subscription_tier": self.default_subscription_tier,
            "admin_emails": self.admin_emails,
            "is_development": self.is_development,
            "is_staging": self.is_staging,
            "is_production": self.is_production,
        }


# Global config instance
config = Config()
