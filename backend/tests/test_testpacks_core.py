from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.testpacks.core import BaseTestPack, get_pack_name_variants, register_test
from app.utils.normalization import normalize_pack_storage_value


class ExamplePack(BaseTestPack):
    @register_test(target_column="A")
    def test_CR9999_1(self):
        return pd.DataFrame({self.trans_ref: ["x"], "test_results": [True]})

    @register_test(target_column="A")
    def test_custom_name(self):
        return pd.DataFrame({self.trans_ref: ["x"], "test_results": [True]})


class EmptyResultPack(BaseTestPack):
    @register_test(target_column="A")
    def test_CR1111_1(self):
        return None


client = TestClient(app)


def _pack(enabled_tests: list[str] | None = None) -> ExamplePack:
    return ExamplePack(pd.DataFrame({"ref": ["x"], "A": [1]}), trans_ref="ref", enabled_tests=enabled_tests)


def test_iter_registered_tests_supports_multiple_filter_formats():
    by_full_name = _pack(enabled_tests=["test_CR9999_1"]).iter_registered_tests()
    by_short_name = _pack(enabled_tests=["custom_name"]).iter_registered_tests()
    by_cr_code = _pack(enabled_tests=["CR9999"]).iter_registered_tests()

    assert [m.__name__ for m in by_full_name] == ["test_CR9999_1"]
    assert [m.__name__ for m in by_short_name] == ["test_custom_name"]
    assert [m.__name__ for m in by_cr_code] == ["test_CR9999_1"]


def test_iter_registered_tests_falls_back_to_all_when_no_match():
    methods = _pack(enabled_tests=["DOES_NOT_EXIST"]).iter_registered_tests()
    assert sorted(m.__name__ for m in methods) == ["test_CR9999_1", "test_custom_name"]


def test_run_with_coverage_handles_none_result_as_zero_evaluated_rows():
    pack = EmptyResultPack(pd.DataFrame({"ref": ["x"], "A": [1]}), trans_ref="ref")
    failures, coverage = pack.run_with_coverage()

    assert failures == []
    assert len(coverage) == 1
    assert coverage[0].evaluated_rows == 0
    assert coverage[0].failed_rows == 0


def test_rules_engine_deduplicates_inherited_tests_across_packs():
    response = client.get("/api/v1/rules-engine")
    assert response.status_code == 200
    data = response.json()

    shared_rule = next(
        r
        for r in data["rules"]
        if r["rule_id"] == "CR0002_1" and r["target_column"] == "Reporting Period (End Date)"
    )
    assert shared_rule["pack"] == "claims, risk_and_premium"


def test_rules_engine_pack_filter_returns_single_pack_only():
    response = client.get("/api/v1/rules-engine", params={"test_pack": "claims"})
    assert response.status_code == 200
    data = response.json()

    assert data["packs"] == ["claims", "risk_and_premium"]
    assert all(row["pack"] == "claims" for row in data["rules"])


def test_pack_name_variants_include_aliases():
    variants = get_pack_name_variants("premium")
    assert variants[0] == "risk_and_premium"
    assert set(variants[1:]) == {"premium", "bordereaux"}


def test_normalize_pack_storage_value_collapses_aliases():
    assert normalize_pack_storage_value("premium") == "risk_and_premium"
    assert normalize_pack_storage_value("bordereaux") == "risk_and_premium"
    assert normalize_pack_storage_value("risk_and_premium") == "risk_and_premium"
