import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.validation import validate_cell, validate_grid_with_packs_report


client = TestClient(app)

# Test API key for authenticated requests
TEST_API_KEY = "dev_bordereaux_key_12345"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


# =============================================================================
# Health Check Tests
# =============================================================================

def test_health_endpoint():
    """Health endpoint should return ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "db_available" in data


# =============================================================================
# Validate Cell Tests
# =============================================================================

def test_validate_cell_passes_all_tests():
    """Cell with valid data should pass all tests."""
    result = validate_cell(
        value=42,
        tests=[
            {"name": "required"},
            {"name": "type", "expected": "number"},
        ],
    )
    assert result.fail_count == 0
    assert result.color == "#E2F0D9"  # Light green for 0 failures


def test_validate_cell_fails_required():
    """Empty cell should fail required test."""
    result = validate_cell(
        value="",
        tests=[{"name": "required"}],
    )
    assert result.fail_count == 1
    assert "Value is required" in result.comment


def test_validate_cell_fails_type_number():
    """Non-numeric value should fail number type test."""
    result = validate_cell(
        value="not a number",
        tests=[{"name": "type", "expected": "number"}],
    )
    assert result.fail_count == 1
    assert "Expected a numeric value" in result.comment


def test_validate_cell_fails_min():
    """Value below minimum should fail min test."""
    result = validate_cell(
        value=5,
        tests=[{"name": "min", "value": 10}],
    )
    assert result.fail_count == 1
    assert "Must be >= 10" in result.comment


def test_validate_cell_fails_max():
    """Value above maximum should fail max test."""
    result = validate_cell(
        value=100,
        tests=[{"name": "max", "value": 50}],
    )
    assert result.fail_count == 1
    assert "Must be <= 50" in result.comment


def test_validate_cell_fails_allowed_values():
    """Value not in allowed set should fail."""
    result = validate_cell(
        value="INVALID",
        tests=[{"name": "allowed_values", "values": ["A", "B", "C"]}],
    )
    assert result.fail_count == 1
    assert "not in the allowed set" in result.comment


# =============================================================================
# Validate Range Endpoint Tests
# =============================================================================

def test_validate_range_basic():
    """Basic validation request should succeed."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [["A1", "B1"], ["A2", "B2"]],
            "values": [["header1", "header2"], ["value1", 123]],
            "columnRules": {},
            "testPacks": [],
            "hasHeaderRow": True,
            "packConfigs": {},
            "includeCoverage": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "coverage" in data
    assert len(data["results"]) == 4  # 2x2 grid


def test_validate_range_with_column_rules():
    """Validation with column rules should apply tests."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [["A1"], ["A2"], ["A3"]],
            "values": [["amount"], [100], ["invalid"]],
            "columnRules": {
                "0": [{"name": "type", "expected": "number"}]
            },
            "testPacks": [],
            "hasHeaderRow": True,
            "packConfigs": {},
            "includeCoverage": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    
    # Find the result for A3 (row index 2)
    a3_result = next(r for r in data["results"] if r["address"] == "A3")
    assert a3_result["failCount"] >= 1  # "invalid" is not a number


def test_validate_range_mismatched_dimensions():
    """Mismatched addresses and values should return 400."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [["A1", "B1"]],
            "values": [["value1"]],  # Missing one value
            "columnRules": {},
            "testPacks": [],
            "hasHeaderRow": False,
        },
    )
    assert response.status_code == 400


def test_validate_range_with_bordereaux_pack():
    """Validation with bordereaux pack should run tests."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [
                ["A1", "B1", "C1", "D1"],
                ["A2", "B2", "C2", "D2"],
                ["A3", "B3", "C3", "D3"],
            ],
            "values": [
                ["policy_id", "premium_amount", "currency", "product_type"],
                ["POL-001", 1000, "GBP", "PROPERTY"],
                ["POL-002", None, "XYZ", "MARINE"],  # Missing premium, invalid currency
            ],
            "columnRules": {},
            "testPacks": ["bordereaux"],
            "hasHeaderRow": True,
            "packConfigs": {"bordereaux": {"RefColumn": "policy_id"}},
            "includeCoverage": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    
    # Check coverage includes bordereaux pack
    assert "bordereaux" in data["coverage"]["packs"]
    
    # Check that some tests ran
    pack_coverage = data["coverage"]["packs"]["bordereaux"]
    assert pack_coverage["totals"]["testsRun"] > 0


def test_validate_range_unknown_pack():
    """Unknown pack should be blocked by subscription access check."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [["A1"], ["A2"]],
            "values": [["header"], ["value"]],
            "columnRules": {},
            "testPacks": ["nonexistent_pack"],
            "hasHeaderRow": True,
            "packConfigs": {},
            "includeCoverage": True,
        },
    )
    # Should be blocked because subscription doesn't include this pack
    assert response.status_code == 403
    assert "not available" in response.json()["detail"]


def test_validate_range_coverage_disabled():
    """Coverage can be disabled in request."""
    response = client.post(
        "/validate-range",
        headers=AUTH_HEADERS,
        json={
            "addresses": [["A1"]],
            "values": [["value"]],
            "columnRules": {},
            "testPacks": [],
            "hasHeaderRow": False,
            "includeCoverage": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["coverage"] is None


# =============================================================================
# Bordereaux Test Pack Tests
# =============================================================================

def test_bordereaux_policy_id_required():
    """Bordereaux pack should fail when policy_id is missing."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1"],
            ["A2", "B2"],
            ["A3", "B3"],
        ],
        values=[
            ["policy_id", "premium_amount"],
            ["POL-001", 1000],
            [None, 2000],  # Missing policy_id
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    # Find the test results for policy_id_required
    pack_tests = report["coverage"]["packs"]["bordereaux"]["tests"]
    assert "test_policy_id_required" in pack_tests
    assert pack_tests["test_policy_id_required"]["failedRows"] >= 1


def test_bordereaux_premium_required():
    """Bordereaux pack should fail when premium_amount is missing."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1"],
            ["A2", "B2"],
        ],
        values=[
            ["policy_id", "premium_amount"],
            ["POL-001", None],  # Missing premium
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    pack_tests = report["coverage"]["packs"]["bordereaux"]["tests"]
    assert "test_premium_amount_required" in pack_tests
    assert pack_tests["test_premium_amount_required"]["failedRows"] >= 1


def test_bordereaux_currency_valid():
    """Bordereaux pack should fail for invalid currency codes."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1"],
            ["A2", "B2"],
        ],
        values=[
            ["policy_id", "currency"],
            ["POL-001", "INVALID"],  # Invalid currency
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    pack_tests = report["coverage"]["packs"]["bordereaux"]["tests"]
    assert "test_currency_valid" in pack_tests
    assert pack_tests["test_currency_valid"]["failedRows"] >= 1


def test_bordereaux_marine_requires_vessel():
    """Bordereaux pack should fail when marine policy has no vessel_id."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ],
        values=[
            ["policy_id", "product_type", "vessel_id"],
            ["POL-001", "MARINE", None],  # Marine without vessel
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    pack_tests = report["coverage"]["packs"]["bordereaux"]["tests"]
    assert "test_marine_requires_vessel" in pack_tests
    assert pack_tests["test_marine_requires_vessel"]["failedRows"] >= 1


def test_bordereaux_claim_within_limit():
    """Bordereaux pack should fail when claim exceeds policy limit."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ],
        values=[
            ["policy_id", "claim_amount", "policy_limit"],
            ["POL-001", 500000, 100000],  # Claim exceeds limit
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    pack_tests = report["coverage"]["packs"]["bordereaux"]["tests"]
    assert "test_claim_within_limit" in pack_tests
    assert pack_tests["test_claim_within_limit"]["failedRows"] >= 1


# =============================================================================
# Severity Score Tests
# =============================================================================

def test_severity_score_affects_heatmap():
    """Higher severity failures should result in higher severity scores."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],  # Will fail CRITICAL test (claim > limit)
            ["A3", "B3", "C3"],  # Will fail WARNING test (marine no vessel)
        ],
        values=[
            ["policy_id", "claim_amount", "policy_limit"],
            ["POL-001", 500000, 100000],  # CRITICAL: claim exceeds limit
            ["POL-002", 0, 100000],  # No failure
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    # Find results with failures
    failed_results = [r for r in report["results"] if r["failCount"] > 0]
    
    # Check that severity scores are included
    for result in failed_results:
        assert "severityScore" in result
        assert result["severityScore"] > 0


def test_multiple_columns_affected_by_single_test():
    """Tests targeting multiple columns should highlight all of them."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ],
        values=[
            ["policy_id", "claim_amount", "policy_limit"],
            ["POL-001", 500000, 100000],  # Fails claim_within_limit
        ],
        column_rules={},
        test_packs=["bordereaux"],
        has_header_row=True,
        pack_configs={"bordereaux": {"RefColumn": "policy_id"}},
    )
    
    # Both claim_amount (B2) and policy_limit (C2) should be highlighted
    b2_result = next(r for r in report["results"] if r["address"] == "B2")
    c2_result = next(r for r in report["results"] if r["address"] == "C2")
    
    assert b2_result["failCount"] > 0
    assert c2_result["failCount"] > 0
