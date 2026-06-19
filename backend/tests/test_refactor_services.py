from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import importlib

field_mapping_module = importlib.import_module("app.services.configuration.field_mapping_service")
rules_engine_module = importlib.import_module("app.services.rules_engine.rules_engine_service")
validation_orchestration_module = importlib.import_module("app.services.validation.validation_orchestration_service")
from app.services.exceptions.exception_service import exception_tagging_service
from app.services.results.results_service import results_domain_service
from app.testpacks.core import BaseTestPack, Severity, register_test
from app.schemas.validation import ValidateRequest


def test_field_mapping_service_estimates_matches_and_confidence(monkeypatch):
    monkeypatch.setattr(
        field_mapping_module,
        "load_pack_field_configuration",
        lambda pack_name: {
            "Territory A": {
                "mandatory": [{"field": "Policy Number"}],
                "conditional": [{"field": "Premium Amount"}],
            }
        },
    )

    result = asyncio.run(
        field_mapping_module.field_mapping_service.estimate_field_mapping(
            test_pack="risk_and_premium",
            territory="territory a",
            headers=["Policy Number", "Premium Amount", "Unknown Header"],
            mandatory_fields=["Policy Number"],
        )
    )

    assert result["estimated_mappings"] == {
        "Policy Number": "Policy Number",
        "Premium Amount": "Premium Amount",
    }
    assert result["matched_count"] == 2
    assert result["unmatched_headers"] == ["Unknown Header"]
    assert result["unmatched_fields"] == []
    assert result["confidence_summary"] == {
        "Policy Number": "high",
        "Premium Amount": "high",
    }


def test_rules_engine_service_merges_duplicate_rules(monkeypatch):
    class AlphaPack(BaseTestPack):
        @register_test(target_columns=["Amount"], description="Amount check", severity=Severity.ERROR)
        def test_CR0001_1(self):
            return None

    class BetaPack(BaseTestPack):
        @register_test(target_columns=["Amount"], description="Amount check", severity=Severity.ERROR)
        def test_CR0001_1(self):
            return None

    monkeypatch.setattr(rules_engine_module, "TEST_PACKS", {"alpha": AlphaPack, "beta": BetaPack})

    response = rules_engine_module.rules_engine_service.get_rules()

    assert response.packs == ["alpha", "beta"]
    assert len(response.rules) == 1
    assert response.rules[0].pack == "alpha, beta"
    assert response.rules[0].rule_id == "CR0001_1"
    assert response.rules[0].target_column == "Amount"


def test_results_service_builds_comparison_and_kpis():
    previous_version = SimpleNamespace(
        id=10,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        version_name=None,
        results_json={
            "version_name": "v1",
            "KPIs": {
                "submissions_failed": 1,
                "tests_failed": 2,
                "total_submissions": 4,
                "total_tests": 5,
                "fields_failed": 3,
                "total_fields": 6,
            },
        },
    )
    current_version = SimpleNamespace(
        id=11,
        created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        version_name="v2",
        results_json={
            "KPIs": {
                "submissions_failed": 0,
                "tests_failed": 0,
                "total_submissions": 1,
                "total_tests": 1,
            }
        },
    )
    saved_versions = [
        SimpleNamespace(version=current_version, workbook_name="Book", sheet_name="Current"),
        SimpleNamespace(version=previous_version, workbook_name="Book", sheet_name="Old"),
    ]

    response = results_domain_service.build_version_comparison(
        saved_versions=saved_versions,
        current_workbook="Book",
        current_sheet="Current",
    )

    assert response.previous_version is not None
    assert response.previous_version.id == 10
    assert response.previous_version.version_name == "v1"
    assert response.previous_version.kpis.submissions_failed == 1
    assert response.trend[0].id == 10
    assert response.trend[1].id == 11
    assert response.trend[1].version_name == "v2"


def test_exception_service_builds_fallback_tagged_cells():
    tagged_cells = exception_tagging_service.build_tagged_cells(
        exception_id="EX-1",
        addresses=["a1", "B2"],
        tagged_cells=[],
        sheet_name=" Sheet 1 ",
        workbook_name="Book.xlsx",
    )

    assert tagged_cells == [
        {
            "address": "A1",
            "exception_id": "EX-1",
            "comment": "Exception tagged: EX-1",
            "fill_color": "#dbeafe",
            "previous_fill_color": "",
            "sheet_name": "Sheet 1",
            "workbook_name": "Book.xlsx",
        },
        {
            "address": "B2",
            "exception_id": "EX-1",
            "comment": "Exception tagged: EX-1",
            "fill_color": "#dbeafe",
            "previous_fill_color": "",
            "sheet_name": "Sheet 1",
            "workbook_name": "Book.xlsx",
        },
    ]


def test_validation_orchestration_service_merges_stored_and_incoming_configs(monkeypatch):
    async def fake_get_config(db, *, organisation_id, user_id, workbook_name, sheet_name, test_pack):
        if test_pack == "risk_and_premium":
            return {"stored": True, "overridden": "from-db"}
        return None

    upsert_calls: list[dict[str, object]] = []

    async def fake_upsert_config(db, *, organisation_id, user_id, workbook_name, sheet_name, test_pack, pack_config):
        upsert_calls.append({"test_pack": test_pack, "pack_config": pack_config})
        return pack_config

    monkeypatch.setattr(validation_orchestration_module, "check_pack_access", lambda subscription, packs: None)
    monkeypatch.setattr(validation_orchestration_module.pack_config_service, "get_config", fake_get_config)
    monkeypatch.setattr(validation_orchestration_module.pack_config_service, "upsert_config", fake_upsert_config)

    payload = ValidateRequest(
        addresses=[["A1"]],
        values=[["value"]],
        testPacks=["claims", "risk_and_premium"],
        packConfigs={
            "claims": {"incoming": 1},
            "risk_and_premium": {"incoming": 2},
        },
        sheetName="Sheet 1",
        workbookName="Book.xlsx",
    )
    subscription = SimpleNamespace(metadata={"is_dev_key": False, "user_id": 7, "organisation_id": 9})

    normalized_packs, effective_configs = asyncio.run(
        validation_orchestration_module.validation_orchestration_service.build_effective_pack_configs(
            payload=payload,
            subscription=subscription,
            db_available=True,
            db=AsyncMock(),
        )
    )

    assert normalized_packs == ["claims", "risk_and_premium"]
    assert effective_configs["claims"] == {"incoming": 1}
    assert effective_configs["risk_and_premium"] == {"stored": True, "overridden": "from-db", "incoming": 2}
    assert [call["test_pack"] for call in upsert_calls] == ["claims", "risk_and_premium"]
