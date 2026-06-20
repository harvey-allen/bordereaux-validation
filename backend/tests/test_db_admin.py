"""Tests for the database admin CLI module."""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Get absolute path to db-admin scripts directory and add to path
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_ADMIN_DIR = os.path.join(_ROOT_DIR, "scripts", "db-admin")
_BACKEND_DIR = os.path.join(_ROOT_DIR, "backend")

# Insert at beginning to ensure our paths take precedence
if _DB_ADMIN_DIR not in sys.path:
    sys.path.insert(0, _DB_ADMIN_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Now import the module
import db_admin  # noqa: E402


class TestGenerateApiKey:
    """Test API key generation."""

    def test_generate_api_key_format(self):
        """API key should have correct format."""
        raw_key, key_hash, key_prefix = db_admin.generate_api_key()

        assert raw_key.startswith("bx_")
        assert len(key_hash) == 64  # SHA-256 hex digest
        assert key_prefix.endswith("...")
        assert len(key_prefix) == 15  # "bx_" + 9 chars + "..."

    def test_generate_api_key_uniqueness(self):
        """Each generated key should be unique."""
        keys = [db_admin.generate_api_key()[0] for _ in range(100)]
        assert len(set(keys)) == 100

    def test_generate_api_key_hash_consistency(self):
        """Hash should be consistent for same key."""
        raw_key, key_hash, _ = db_admin.generate_api_key()
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert key_hash == expected_hash


class TestOrganisationOperations:
    """Test organisation CRUD operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def mock_session_maker(self, mock_session):
        """Create a mock session maker context manager."""

        class MockSessionMaker:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        return MockSessionMaker

    def test_list_organisations_empty(self, mock_session, mock_session_maker, capsys):
        """List organisations when none exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.list_organisations())

        captured = capsys.readouterr()
        assert "No organisations found" in captured.out

    def test_list_organisations_with_results(self, mock_session, mock_session_maker, capsys):
        """List organisations with results."""
        # Mock organisations
        org1 = SimpleNamespace(id=1, name="Org One", created_at=datetime.now(timezone.utc))
        org2 = SimpleNamespace(id=2, name="Org Two", created_at=datetime.now(timezone.utc))

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [org1, org2]
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.list_organisations())

        captured = capsys.readouterr()
        assert "Org One" in captured.out
        assert "Org Two" in captured.out
        assert "Total: 2" in captured.out

    def test_get_organisation_found(self, mock_session, mock_session_maker, capsys):
        """Get organisation by ID when found."""
        org = SimpleNamespace(id=1, name="Test Org", created_at=datetime.now(timezone.utc))

        # First call for org, second for users count
        mock_result_org = MagicMock()
        mock_result_org.scalar_one_or_none.return_value = org

        mock_result_users = MagicMock()
        mock_result_users.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_result_org, mock_result_users]

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.get_organisation(org_id=1))

        captured = capsys.readouterr()
        assert "Test Org" in captured.out
        assert "ID:         1" in captured.out

    def test_get_organisation_not_found(self, mock_session, mock_session_maker):
        """Get organisation when not found should exit."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(db_admin.get_organisation(org_id=999))

        assert exc_info.value.code == 1

    def test_create_organisation_success(self, mock_session, mock_session_maker, capsys):
        """Create organisation successfully."""

        async def mock_refresh(obj):
            obj.id = 1

        mock_session.refresh = mock_refresh

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.create_organisation("New Org"))

        captured = capsys.readouterr()
        assert "Organisation created successfully" in captured.out
        assert "New Org" in captured.out


class TestUserOperations:
    """Test user CRUD operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def mock_session_maker(self, mock_session):
        """Create a mock session maker context manager."""

        class MockSessionMaker:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                pass

        return MockSessionMaker

    def test_list_users_empty(self, mock_session, mock_session_maker, capsys):
        """List users when none exist."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.list_users())

        captured = capsys.readouterr()
        assert "No users found" in captured.out

    def test_list_users_with_results(self, mock_session, mock_session_maker, capsys):
        """List users with results."""
        user = SimpleNamespace(
            id=1,
            email="user@example.com",
            tier="bordereaux",
            is_active=True,
            api_key_prefix="bx_abc...",
        )

        mock_result = MagicMock()
        mock_result.all.return_value = [(user, "Test Org")]
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.list_users())

        captured = capsys.readouterr()
        assert "user@example.com" in captured.out
        assert "Test Org" in captured.out
        assert "Total: 1" in captured.out

    def test_get_user_found(self, mock_session, mock_session_maker, capsys):
        """Get user by ID when found."""
        user = SimpleNamespace(
            id=1,
            email="user@example.com",
            display_name="Test User",
            excel_user_id="excel_123",
            organisation_id=1,
            tier="bordereaux",
            is_active=True,
            api_key_prefix="bx_abc...",
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            last_used_at=None,
        )

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (user, "Test Org")
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.get_user(user_id=1))

        captured = capsys.readouterr()
        assert "user@example.com" in captured.out
        assert "Test User" in captured.out
        assert "Test Org" in captured.out

    def test_get_user_not_found(self, mock_session, mock_session_maker):
        """Get user when not found should exit."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(db_admin.get_user(user_id=999))

        assert exc_info.value.code == 1

    def test_create_user_success(self, mock_session, mock_session_maker, capsys):
        """Create user successfully."""
        # Mock organisation exists
        org = SimpleNamespace(id=1, name="Test Org")
        mock_org_result = MagicMock()
        mock_org_result.scalar_one_or_none.return_value = org

        mock_session.execute.return_value = mock_org_result

        async def mock_refresh(obj):
            obj.id = 1

        mock_session.refresh = mock_refresh

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            asyncio.run(db_admin.create_user(
                email="new@example.com",
                organisation_id=1,
                tier="bordereaux",
            ))

        captured = capsys.readouterr()
        assert "User created successfully" in captured.out
        assert "new@example.com" in captured.out
        assert "API KEY" in captured.out

    def test_create_user_org_not_found(self, mock_session, mock_session_maker):
        """Create user with non-existent organisation should exit."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(db_admin.create_user(
                    email="new@example.com",
                    organisation_id=999,
                ))

        assert exc_info.value.code == 1

    def test_create_user_invalid_tier(self, mock_session, mock_session_maker):
        """Create user with invalid tier should exit."""
        org = SimpleNamespace(id=1, name="Test Org")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org
        mock_session.execute.return_value = mock_result

        with patch.object(db_admin, "async_session_maker", return_value=mock_session_maker()):
            with pytest.raises(SystemExit) as exc_info:
                asyncio.run(db_admin.create_user(
                    email="new@example.com",
                    organisation_id=1,
                    tier="invalid_tier",
                ))

        assert exc_info.value.code == 1


class TestCliParsing:
    """Test CLI argument parsing."""

    def test_org_list_command(self):
        """Verify module has expected CLI handlers."""
        assert hasattr(db_admin, "org_cli")
        assert hasattr(db_admin, "user_cli")
        assert hasattr(db_admin, "main")

    def test_module_has_all_operations(self):
        """Verify module exports all CRUD operations."""
        # Organisation operations
        assert hasattr(db_admin, "list_organisations")
        assert hasattr(db_admin, "get_organisation")
        assert hasattr(db_admin, "create_organisation")
        assert hasattr(db_admin, "update_organisation")
        assert hasattr(db_admin, "delete_organisation")

        # User operations
        assert hasattr(db_admin, "list_users")
        assert hasattr(db_admin, "get_user")
        assert hasattr(db_admin, "create_user")
        assert hasattr(db_admin, "update_user")
        assert hasattr(db_admin, "delete_user")
        assert hasattr(db_admin, "activate_user")
        assert hasattr(db_admin, "deactivate_user")
        assert hasattr(db_admin, "regenerate_api_key")
