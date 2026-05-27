"""Tests for authentication, subscriptions, and rate limiting."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth import (
    RateLimitState,
    Subscription,
    SubscriptionStore,
    SubscriptionTier,
    TIER_CONFIGS,
)
from app.main import app

client = TestClient(app)


# =============================================================================
# Subscription Store Tests
# =============================================================================

class TestSubscriptionStore:
    """Tests for the subscription store."""

    def test_dev_key_exists(self):
        """Development key should be created automatically."""
        store = SubscriptionStore()
        sub = store.get_subscription("dev_bordereaux_key_12345")
        assert sub is not None
        assert sub.tier == SubscriptionTier.BORDEREAUX
        assert sub.is_active

    def test_generate_api_key(self):
        """Should generate valid API keys."""
        store = SubscriptionStore()
        key = store.generate_api_key(
            tier=SubscriptionTier.TRIAL,
            owner_email="test@example.com",
        )
        
        assert key.startswith("bx_tri_")
        sub = store.get_subscription(key)
        assert sub is not None
        assert sub.tier == SubscriptionTier.TRIAL
        assert sub.owner_email == "test@example.com"

    def test_generate_key_with_expiry(self):
        """Should create keys with expiration dates."""
        store = SubscriptionStore()
        key = store.generate_api_key(
            tier=SubscriptionTier.TRIAL,
            owner_email="trial@example.com",
            expires_in_days=30,
        )
        
        sub = store.get_subscription(key)
        assert sub.expires_at is not None
        assert not sub.is_expired

    def test_revoke_key(self):
        """Should be able to revoke API keys."""
        store = SubscriptionStore()
        key = store.generate_api_key(
            tier=SubscriptionTier.TRIAL,
            owner_email="revoke@example.com",
        )
        
        assert store.get_subscription(key).is_active
        store.revoke_key(key)
        assert not store.get_subscription(key).is_active

    def test_invalid_key_returns_none(self):
        """Invalid API keys should return None."""
        store = SubscriptionStore()
        assert store.get_subscription("invalid_key_123") is None


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_state_tracks_requests(self):
        """Should track requests over time."""
        state = RateLimitState()
        
        state.record_request()
        state.record_request()
        state.record_request()
        
        assert state.requests_this_minute == 3
        assert state.requests_today == 3

    def test_rate_limit_cleans_old_requests(self):
        """Should remove old requests from tracking."""
        state = RateLimitState()
        
        # Add old request (older than a day)
        state.minute_requests.append(time.time() - 120)  # 2 minutes ago
        state.day_requests.append(time.time() - 90000)   # More than a day ago
        
        # Add recent request
        state.record_request()
        
        assert state.requests_this_minute == 1
        assert state.requests_today == 1

    def test_check_rate_limit_allows_within_limits(self):
        """Should allow requests within rate limits."""
        store = SubscriptionStore()
        sub = store.get_subscription("dev_bordereaux_key_12345")
        
        allowed, error = store.check_rate_limit(sub)
        assert allowed
        assert error is None

    def test_check_rate_limit_blocks_over_minute_limit(self):
        """Should block requests over minute limit."""
        store = SubscriptionStore()
        key = store.generate_api_key(SubscriptionTier.TRIAL, "test@example.com")
        sub = store.get_subscription(key)
        
        # Exhaust minute limit (5 for TRIAL tier)
        for _ in range(5):
            store.record_request(sub)
        
        allowed, error = store.check_rate_limit(sub)
        assert not allowed
        assert "requests/minute" in error


# =============================================================================
# API Authentication Tests
# =============================================================================

class TestAPIAuthentication:
    """Tests for API authentication endpoints."""

    def test_health_no_auth_required(self):
        """Health endpoint should not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "db_available" in data

    def test_validate_requires_auth(self):
        """Validation endpoint should require authentication."""
        response = client.post(
            "/validate-range",
            json={
                "addresses": [["A1"]],
                "values": [["test"]],
                "testPacks": ["bordereaux"],
            },
        )
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_validate_with_valid_key(self):
        """Validation should work with valid API key."""
        response = client.post(
            "/validate-range",
            headers={"X-API-Key": "dev_bordereaux_key_12345"},
            json={
                "addresses": [["A1", "B1"], ["A2", "B2"]],
                "values": [["Unique Market Reference (UMR)", "premium_amount"], ["POL001", "1000"]],
                "testPacks": ["bordereaux"],
                "hasHeaderRow": True,
                "packConfigs": {"bordereaux": {"UMR": "Unique Market Reference (UMR)"}},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "usage" in data

    def test_validate_with_invalid_key(self):
        """Validation should fail with invalid API key."""
        response = client.post(
            "/validate-range",
            headers={"X-API-Key": "invalid_key"},
            json={
                "addresses": [["A1"]],
                "values": [["test"]],
            },
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_api_key_via_query_param(self):
        """Should accept API key via query parameter."""
        response = client.get(
            "/api/v1/subscription?api_key=dev_bordereaux_key_12345"
        )
        assert response.status_code == 200

    def test_usage_endpoint(self):
        """Usage endpoint should return usage statistics."""
        response = client.get(
            "/api/v1/usage",
            headers={"X-API-Key": "dev_bordereaux_key_12345"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "tier" in data
        assert "requests_today" in data
        assert "daily_limit" in data
        assert "daily_remaining" in data

    def test_subscription_info_endpoint(self):
        """Subscription endpoint should return subscription details."""
        response = client.get(
            "/api/v1/subscription",
            headers={"X-API-Key": "dev_bordereaux_key_12345"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "bordereaux"
        assert data["is_active"] is True


# =============================================================================
# Tier Restrictions Tests
# =============================================================================

class TestTierRestrictions:
    """Tests for subscription tier restrictions."""

    def test_tier_configs_exist(self):
        """All tiers should have configurations."""
        for tier in SubscriptionTier:
            assert tier in TIER_CONFIGS
            config = TIER_CONFIGS[tier]
            assert config.requests_per_day > 0
            assert config.requests_per_minute > 0
            assert config.max_cells_per_request > 0

    def test_trial_tier_has_pack_restrictions(self):
        """TRIAL tier should have limited pack access."""
        config = TIER_CONFIGS[SubscriptionTier.TRIAL]
        assert config.allowed_packs is not None
        assert "bordereaux" in config.allowed_packs

    def test_bordereaux_tier_includes_bordereaux_pack(self):
        """BORDEREAUX tier should include the bordereaux pack."""
        config = TIER_CONFIGS[SubscriptionTier.BORDEREAUX]
        assert config.allowed_packs is not None
        assert "bordereaux" in config.allowed_packs

    def test_bordereaux_has_higher_limits(self):
        """BORDEREAUX tier should have higher limits than TRIAL."""
        bordereaux = TIER_CONFIGS[SubscriptionTier.BORDEREAUX]
        trial = TIER_CONFIGS[SubscriptionTier.TRIAL]
        
        assert bordereaux.requests_per_day > trial.requests_per_day
        assert bordereaux.max_cells_per_request > trial.max_cells_per_request


# =============================================================================
# Cell Limit Tests
# =============================================================================

class TestCellLimits:
    """Tests for cell count limits per request."""

    def test_request_within_cell_limit(self):
        """Requests within cell limit should succeed."""
        # Create small request (4 cells)
        response = client.post(
            "/validate-range",
            headers={"X-API-Key": "dev_bordereaux_key_12345"},
            json={
                "addresses": [["A1", "B1"], ["A2", "B2"]],
                "values": [["col1", "col2"], ["val1", "val2"]],
            },
        )
        assert response.status_code == 200
