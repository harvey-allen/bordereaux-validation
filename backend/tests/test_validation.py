import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.validation import get_pack_mandatory_fields, validate_cell, validate_grid_with_packs_report


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
        pack_configs={"bordereaux": {"ID": "policy_id"}},
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
        pack_configs={"bordereaux": {"ID": "policy_id"}},
    )
    
    # Both claim_amount (B2) and policy_limit (C2) should be highlighted
    b2_result = next(r for r in report["results"] if r["address"] == "B2")
    c2_result = next(r for r in report["results"] if r["address"] == "C2")
    
    assert b2_result["failCount"] > 0
    assert c2_result["failCount"] > 0


def test_field_mappings_enable_model_based_tests_with_codes():
    """Missing model fields should be tested only when mapped from sheet columns."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
            ["A3", "B3", "C3"],
        ],
        values=[
            ["policy_number", "premium_currency", "gross_written_premium"],
            ["POL-001", "GBP", 1000],
            ["", "INVALID", None],
        ],
        column_rules={},
        test_packs=["risk_and_premium"],
        has_header_row=True,
        pack_configs={
            "risk_and_premium": {
                "ID": "policy_number",
                "fieldMappings": {
                    "policy_id": "policy_number",
                    "currency": "premium_currency",
                    "premium_amount": "gross_written_premium",
                },
                "enabledTests": ["Bpolicy_id1", "Bcurrency1", "Bpremium_amount1"],
            }
        },
    )

    premium_tests = report["coverage"]["packs"]["risk_and_premium"]["tests"]
    assert "test_policy_id_required" in premium_tests
    assert premium_tests["test_policy_id_required"]["testCode"] == "Bpolicy_id1"
    assert premium_tests["test_currency_valid"]["testCode"] == "Bcurrency1"
    assert premium_tests["test_premium_amount_required"]["testCode"] == "Bpremium_amount1"

    assert premium_tests["test_policy_id_required"]["failedRows"] >= 1
    assert premium_tests["test_currency_valid"]["failedRows"] >= 1
    assert premium_tests["test_premium_amount_required"]["failedRows"] >= 1


def test_missing_default_columns_produce_critical_header_errors():
    """Missing assumed default columns should raise CRITICAL header failures."""
    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ],
        values=[
            ["policy_number", "premium_currency", "gross_written_premium"],
            ["POL-001", "GBP", 1000],
        ],
        column_rules={},
        test_packs=["risk_and_premium"],
        has_header_row=True,
        pack_configs={
            "risk_and_premium": {
                "ID": "policy_number",
                "territory": "UK",
                "enabledTests": ["Bpolicy_id1", "Bcurrency1", "Bpremium_amount1"],
            }
        },
    )

    header_results = [r for r in report["results"] if r["rowIndex"] == 0]
    assert any(r["failCount"] > 0 for r in header_results)
    assert any("Bheaders1" in r["comment"] for r in header_results if r["failCount"] > 0)
    assert "test_required_headers_present" in report["coverage"]["packs"]["risk_and_premium"]["tests"]
    assert report["coverage"]["packs"]["risk_and_premium"]["tests"]["test_required_headers_present"]["failedRows"] == 1


def test_default_missing_columns_resolved_by_field_mappings():
    """Mapping sheet names to model defaults should clear missing-default-column header errors."""
    premium_required_fields = get_pack_mandatory_fields("risk_and_premium", "UK")
    full_field_mapping = {
        field: "policy_number"
        for field in premium_required_fields
    }
    full_field_mapping.update(
        {
            "currency": "premium_currency",
            "premium_amount": "gross_written_premium",
            "policy_id": "policy_number",
            "premium_currency": "premium_currency",
            "gross_written_premium": "gross_written_premium",
        }
    )

    report = validate_grid_with_packs_report(
        addresses=[
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
        ],
        values=[
            ["policy_number", "premium_currency", "gross_written_premium"],
            ["POL-001", "GBP", 1000],
        ],
        column_rules={},
        test_packs=["risk_and_premium"],
        has_header_row=True,
        pack_configs={
            "risk_and_premium": {
                "ID": "policy_number",
                "territory": "UK",
                "fieldMappings": full_field_mapping,
                "enabledTests": ["Bpolicy_id1", "Bcurrency1", "Bpremium_amount1"],
            }
        },
    )

    header_results = [r for r in report["results"] if r["rowIndex"] == 0]
    assert all("Bheaders1" not in r["comment"] for r in header_results)
    assert report["coverage"]["packs"]["risk_and_premium"]["tests"]["test_required_headers_present"]["failedRows"] == 0
