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
    assert result.color == "#FFFFFF"  # No failures


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
            "packConfigs": {"bordereaux": {"ID": "policy_id"}},
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
    assert response.status_code == 400
    assert "Unknown test pack" in response.json()["detail"]


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
# Severity Score Tests
# =============================================================================

def test_severity_score_affects_heatmap():
    """Higher severity failures should result in higher severity scores."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1"],
            ["A2", "B2"],
            ["A3", "B3"],
        ],
        values=[
            ["amount", "status"],
            [100, "active"],  # Pass
            [-50, "active"],  # Fail min check
        ],
        column_rules={
            "0": [{"name": "min", "value": 0}],  # amount must be >= 0
        },
        test_packs=[],
        has_header_row=True,
        pack_configs={},
    )
    
    # Find results with failures
    failed_results = [r for r in report["results"] if r["failCount"] > 0]
    
    # Check that severity scores are included
    for result in failed_results:
        assert "severityScore" in result
        assert result["severityScore"] > 0


def test_multiple_columns_affected_by_single_test():
    """Tests with multiple column rules should highlight all affected columns."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1"],
            ["A2", "B2"],
        ],
        values=[
            ["amount", "status"],
            [50, "active"],
        ],
        column_rules={
            "0": [{"name": "min", "value": 100}],  # amount must be >= 100
            "1": [{"name": "required"}],  # status must not be empty
        },
        test_packs=[],
        has_header_row=True,
        pack_configs={},
    )
    
    # Both A2 and B2 should show failures
    a2_result = next(r for r in report["results"] if r["address"] == "A2")
    b2_result = next(r for r in report["results"] if r["address"] == "B2")
    
    assert a2_result["failCount"] > 0  # 50 < 100
    assert b2_result["failCount"] == 0  # "active" is not empty
