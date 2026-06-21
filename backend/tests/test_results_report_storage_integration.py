from __future__ import annotations

import asyncio
import base64
import io
from datetime import datetime, timezone
from types import SimpleNamespace

from openpyxl import load_workbook

from app.database import ValidationResultPayload
from app.repositories.results.results_repository import ResultsRepository
from app.services.results.report_storage_service import (
    ReportDeleteError,
    ReportObjectNotFoundError,
    ReportUploadError,
    report_storage_service,
)
from app.services.results.results_persistence_service import (
    delete_results_version_by_id,
    get_results_version_payload_by_id,
    save_results_version,
    update_results_version_by_id,
)


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.deleted: list[object] = []
        self._next_id = 100
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", self._next_id)
                self._next_id += 1

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _obj):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)


def test_save_results_version_uploads_report_payload_to_s3(monkeypatch):
    session = _FakeSession()

    async def fake_get_or_create(*_args, **_kwargs):
        return SimpleNamespace(id=12)

    async def fake_get_version(*_args, **_kwargs):
        return None

    async def fake_get_payload(*_args, **_kwargs):
        return None

    async def fake_get_org_name(*_args, **_kwargs):
        return "acme"

    uploaded: list[dict[str, object]] = []

    async def fake_upload(*, s3_key: str, payload: dict[str, object]):
        uploaded.append({"s3_key": s3_key, "payload": payload})

    monkeypatch.setattr(
        "app.services.results.results_persistence_service._get_or_create_sheet_key",
        fake_get_or_create,
    )
    monkeypatch.setattr(ResultsRepository, "get_version_for_sheet_key_pack", fake_get_version)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_organisation_name_by_id", fake_get_org_name)
    monkeypatch.setattr(
        report_storage_service,
        "generate_s3_key",
        lambda **_kwargs: "acme/101.json",
    )
    monkeypatch.setattr(report_storage_service, "upload_report", fake_upload)

    version = asyncio.run(
        save_results_version(
            session,
            organisation_id=12,
            user_id=1,
            workbook_name="Book.xlsx",
            sheet_name="Sheet1",
            test_pack="bordereaux",
            failed_tests=[],
            passed_tests=["T-1"],
            mapped_headers={"Header A": "field_a"},
            saved_data=[{"umr": "U-1"}],
        )
    )

    assert version.id == 100
    assert session.commits == 1
    assert session.rollbacks == 0
    assert uploaded == [
        {
            "s3_key": "acme/101.json",
            "payload": {
                "mapped_headers": {"Header A": "field_a"},
                "saved_data": [{"umr": "U-1"}],
            },
        }
    ]
    payload_row = next(item for item in session.added if isinstance(item, ValidationResultPayload))
    assert payload_row.s3_location == "acme/101.json"
    assert payload_row.sheet_key_id == 12


def test_save_results_version_rolls_back_on_upload_failure(monkeypatch):
    session = _FakeSession()

    async def fake_get_or_create(*_args, **_kwargs):
        return SimpleNamespace(id=9)

    async def fake_get_version(*_args, **_kwargs):
        return None

    async def fake_get_payload(*_args, **_kwargs):
        return None

    async def fake_get_org_name(*_args, **_kwargs):
        return "acme"

    async def fail_upload(*, s3_key: str, payload: dict[str, object]):
        raise ReportUploadError(f"failed {s3_key}")

    monkeypatch.setattr(
        "app.services.results.results_persistence_service._get_or_create_sheet_key",
        fake_get_or_create,
    )
    monkeypatch.setattr(ResultsRepository, "get_version_for_sheet_key_pack", fake_get_version)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_organisation_name_by_id", fake_get_org_name)
    monkeypatch.setattr(report_storage_service, "generate_s3_key", lambda **_kwargs: "acme/101.json")
    monkeypatch.setattr(report_storage_service, "upload_report", fail_upload)

    try:
        asyncio.run(
            save_results_version(
                session,
                organisation_id=9,
                user_id=1,
                workbook_name="Book.xlsx",
                sheet_name="Sheet1",
                test_pack="bordereaux",
                failed_tests=[],
                passed_tests=[],
                mapped_headers={},
                saved_data=[],
            )
        )
        raise AssertionError("Expected ReportUploadError")
    except ReportUploadError:
        pass

    assert session.commits == 0
    assert session.rollbacks == 1


def test_save_results_version_uploads_excel_payload_to_s3(monkeypatch):
    session = _FakeSession()

    async def fake_get_or_create(*_args, **_kwargs):
        return SimpleNamespace(id=12)

    async def fake_get_version(*_args, **_kwargs):
        return None

    async def fake_get_payload(*_args, **_kwargs):
        return None

    async def fake_get_org_name(*_args, **_kwargs):
        return "acme"

    uploaded_bytes: list[dict[str, object]] = []

    async def fake_upload_bytes(*, s3_key: str, body: bytes, content_type: str):
        uploaded_bytes.append({
            "s3_key": s3_key,
            "body": body,
            "content_type": content_type,
        })

    monkeypatch.setattr(
        "app.services.results.results_persistence_service._get_or_create_sheet_key",
        fake_get_or_create,
    )
    monkeypatch.setattr(ResultsRepository, "get_version_for_sheet_key_pack", fake_get_version)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_organisation_name_by_id", fake_get_org_name)
    monkeypatch.setattr(report_storage_service, "generate_s3_key", lambda **_kwargs: "acme/101.xlsx")
    monkeypatch.setattr(report_storage_service, "upload_report_bytes", fake_upload_bytes)

    excel_b64 = base64.b64encode(b"excel-workbook-binary").decode("ascii")
    version = asyncio.run(
        save_results_version(
            session,
            organisation_id=12,
            user_id=1,
            workbook_name="Book.xlsx",
            sheet_name="Sheet1",
            test_pack="bordereaux",
            failed_tests=[],
            passed_tests=["T-1"],
            mapped_headers={"Header A": "field_a"},
            saved_data=[{"umr": "U-1"}],
            excel_file_base64=excel_b64,
        )
    )

    assert version.id == 100
    assert uploaded_bytes == [
        {
            "s3_key": "acme/101.xlsx",
            "body": b"excel-workbook-binary",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    ]


def test_save_results_version_uploads_single_worksheet_xlsx_from_snapshot(monkeypatch):
    session = _FakeSession()

    async def fake_get_or_create(*_args, **_kwargs):
        return SimpleNamespace(id=12)

    async def fake_get_version(*_args, **_kwargs):
        return None

    async def fake_get_payload(*_args, **_kwargs):
        return None

    async def fake_get_org_name(*_args, **_kwargs):
        return "acme"

    uploaded_bytes: list[dict[str, object]] = []

    async def fake_upload_bytes(*, s3_key: str, body: bytes, content_type: str):
        uploaded_bytes.append(
            {
                "s3_key": s3_key,
                "body": body,
                "content_type": content_type,
            }
        )

    monkeypatch.setattr(
        "app.services.results.results_persistence_service._get_or_create_sheet_key",
        fake_get_or_create,
    )
    monkeypatch.setattr(ResultsRepository, "get_version_for_sheet_key_pack", fake_get_version)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_organisation_name_by_id", fake_get_org_name)
    monkeypatch.setattr(report_storage_service, "generate_s3_key", lambda **_kwargs: "acme/101.xlsx")
    monkeypatch.setattr(report_storage_service, "upload_report_bytes", fake_upload_bytes)

    snapshot = {
        "source_sheet_name": "Source Sheet",
        "mapped_headers": {"UMR": "umr"},
        "saved_data": [{"UMR": "A123"}],
        "validation_results": [
            {
                "address": "A2",
                "rowIndex": 1,
                "columnIndex": 0,
                "failCount": 1,
                "severityScore": 2,
                "comment": "Invalid value",
            }
        ],
    }

    version = asyncio.run(
        save_results_version(
            session,
            organisation_id=12,
            user_id=1,
            workbook_name="Book.xlsx",
            sheet_name="Sheet1",
            test_pack="bordereaux",
            failed_tests=[],
            passed_tests=["T-1"],
            mapped_headers={"UMR": "umr"},
            saved_data=[{"UMR": "A123"}],
            worksheet_snapshot=snapshot,
        )
    )

    assert version.id == 100
    assert len(uploaded_bytes) == 1
    assert uploaded_bytes[0]["s3_key"] == "acme/101.xlsx"
    assert uploaded_bytes[0]["content_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    workbook = load_workbook(io.BytesIO(uploaded_bytes[0]["body"]))
    assert workbook.sheetnames == ["Source Sheet"]
    sheet = workbook["Source Sheet"]
    assert sheet["A1"].value == "UMR"
    assert sheet["A2"].value == "A123"
    assert sheet["A2"].comment is not None
    assert sheet["A2"].comment.text == "Invalid value"


def test_get_results_version_payload_downloads_excel_from_s3(monkeypatch):
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(
        id=88,
        test_pack="bordereaux",
        version_name="v2",
        results_json={},
        tagged_cells_json=[],
        created_at=now,
        updated_at=now,
    )
    sheet_key = SimpleNamespace(id=22, workbook_name="Book.xlsx", sheet_name="Sheet Source")
    payload = SimpleNamespace(version_name="v2", s3_location="acme/88.xlsx")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, sheet_key

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    async def fake_get_pack_config(*_args, **_kwargs):
        return None

    async def fake_get_latest_pack_config(*_args, **_kwargs):
        return None

    async def fake_download_bytes(*, s3_key: str):
        assert s3_key == "acme/88.xlsx"
        return b"excel-workbook-binary"

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_pack_config_for_user_sheet_pack", fake_get_pack_config)
    monkeypatch.setattr(ResultsRepository, "get_latest_pack_config_for_sheet_pack", fake_get_latest_pack_config)
    monkeypatch.setattr(report_storage_service, "download_report_bytes", fake_download_bytes)

    data = asyncio.run(
        get_results_version_payload_by_id(
            _FakeSession(),
            organisation_id=5,
            user_id=1,
            version_id=88,
        )
    )

    assert data is not None
    assert data["mapped_headers"] == {}
    assert data["saved_data"] == []
    assert data["excel_file_base64"] == base64.b64encode(b"excel-workbook-binary").decode("ascii")
    assert data["excel_source_sheet_name"] == "Sheet Source"


def test_get_results_version_payload_downloads_from_s3(monkeypatch):
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(
        id=77,
        test_pack="bordereaux",
        version_name="v1",
        results_json={},
        tagged_cells_json=[],
        created_at=now,
        updated_at=now,
    )
    sheet_key = SimpleNamespace(id=33, workbook_name="Book.xlsx", sheet_name="Sheet1")
    payload = SimpleNamespace(version_name="v1", s3_location="5/77/88.json")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, sheet_key

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    async def fake_get_pack_config(*_args, **_kwargs):
        return None

    async def fake_get_latest_pack_config(*_args, **_kwargs):
        return None

    async def fake_download(*, s3_key: str):
        assert s3_key == "5/77/88.json"
        return {"mapped_headers": {"A": "field_a"}, "saved_data": [{"id": "X"}]}

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_pack_config_for_user_sheet_pack", fake_get_pack_config)
    monkeypatch.setattr(ResultsRepository, "get_latest_pack_config_for_sheet_pack", fake_get_latest_pack_config)
    monkeypatch.setattr(report_storage_service, "download_report", fake_download)

    data = asyncio.run(
        get_results_version_payload_by_id(
            _FakeSession(),
            organisation_id=5,
            user_id=1,
            version_id=77,
        )
    )

    assert data is not None
    assert data["mapped_headers"] == {"A": "field_a"}
    assert data["saved_data"] == [{"id": "X"}]


def test_update_results_version_overwrites_existing_s3_object(monkeypatch):
    session = _FakeSession()
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(
        id=41,
        test_pack="bordereaux",
        version_name="existing",
        results_json={},
        tagged_cells_json=[],
        created_at=now,
        updated_at=now,
    )
    payload = SimpleNamespace(
        id=51,
        s3_location="3/41/51.json",
        version_name="existing",
        updated_at=now,
    )

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, SimpleNamespace(id=2)

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    uploads: list[str] = []

    async def fake_upload(*, s3_key: str, payload: dict[str, object]):
        uploads.append(s3_key)
        assert payload["saved_data"] == [{"id": "UMR-9"}]

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(report_storage_service, "upload_report", fake_upload)

    updated = asyncio.run(
        update_results_version_by_id(
            session,
            organisation_id=3,
            user_id=1,
            version_id=41,
            test_pack="bordereaux",
            failed_tests=[],
            passed_tests=["T-2"],
            mapped_headers={"A": "a"},
            saved_data=[{"id": "UMR-9"}],
        )
    )

    assert updated is version
    assert uploads == ["3/41/51.json"]
    assert payload.s3_location == "3/41/51.json"


def test_delete_results_version_by_id_deletes_s3_object(monkeypatch):
    session = _FakeSession()
    version = SimpleNamespace(id=15)
    payload = SimpleNamespace(s3_location="7/15/22.json")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, SimpleNamespace(id=1)

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    deleted_keys: list[str] = []

    async def fake_delete_report(*, s3_key: str):
        deleted_keys.append(s3_key)

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(report_storage_service, "delete_report", fake_delete_report)

    deleted = asyncio.run(
        delete_results_version_by_id(
            session,
            organisation_id=7,
            version_id=15,
        )
    )

    assert deleted is True
    assert deleted_keys == ["7/15/22.json"]
    assert session.deleted == [version]


def test_get_results_version_payload_raises_when_s3_object_missing(monkeypatch):
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(
        id=99,
        test_pack="bordereaux",
        version_name=None,
        results_json={},
        tagged_cells_json=[],
        created_at=now,
        updated_at=now,
    )
    sheet_key = SimpleNamespace(id=4, workbook_name="Book.xlsx", sheet_name="Sheet1")
    payload = SimpleNamespace(version_name=None, s3_location="7/99/100.json")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, sheet_key

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    async def fake_get_pack_config(*_args, **_kwargs):
        return None

    async def fake_get_latest_pack_config(*_args, **_kwargs):
        return None

    async def fail_download(*, s3_key: str):
        raise ReportObjectNotFoundError(s3_key)

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_pack_config_for_user_sheet_pack", fake_get_pack_config)
    monkeypatch.setattr(ResultsRepository, "get_latest_pack_config_for_sheet_pack", fake_get_latest_pack_config)
    monkeypatch.setattr(report_storage_service, "download_report", fail_download)

    try:
        asyncio.run(
            get_results_version_payload_by_id(
                _FakeSession(),
                organisation_id=7,
                user_id=1,
                version_id=99,
            )
        )
        raise AssertionError("Expected ReportObjectNotFoundError")
    except ReportObjectNotFoundError:
        pass


def test_delete_results_version_by_id_logs_and_continues_on_delete_failure(monkeypatch):
    session = _FakeSession()
    version = SimpleNamespace(id=55)
    payload = SimpleNamespace(s3_location="8/55/66.json")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, SimpleNamespace(id=1)

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    async def fail_delete(*, s3_key: str):
        raise ReportDeleteError(s3_key)

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(report_storage_service, "delete_report", fail_delete)

    deleted = asyncio.run(
        delete_results_version_by_id(
            session,
            organisation_id=8,
            version_id=55,
        )
    )

    assert deleted is True
    assert session.deleted == [version]
    assert session.commits == 1


def test_get_results_version_payload_prefers_saved_version_sheet_key_pack_config(monkeypatch):
    now = datetime.now(timezone.utc)
    version = SimpleNamespace(
        id=111,
        user_id=99,
        test_pack="bordereaux",
        version_name="v-owner",
        results_json={},
        tagged_cells_json=[],
        created_at=now,
        updated_at=now,
    )
    sheet_key = SimpleNamespace(id=5, workbook_name="Book.xlsx", sheet_name="Sheet1")
    payload = SimpleNamespace(version_name="v-owner", s3_location="acme/111.xlsx")

    async def fake_get_version_by_id(*_args, **_kwargs):
        return version, sheet_key

    async def fake_get_payload(*_args, **_kwargs):
        return payload

    pack_lookup_calls: list[int] = []

    async def fake_get_pack_config(*_args, **kwargs):
        pack_lookup_calls.append(int(kwargs["user_id"]))
        if int(kwargs["user_id"]) == 99:
            return SimpleNamespace(config_json={"ID": "UMR", "territory": "UK"})
        return None

    async def fake_get_latest_pack_config(*_args, **_kwargs):
        raise AssertionError("latest fallback should not be used when saved owner config exists")

    async def fake_download_bytes(*, s3_key: str):
        assert s3_key == "acme/111.xlsx"
        return b"excel-workbook-binary"

    monkeypatch.setattr(ResultsRepository, "get_version_by_id_for_org", fake_get_version_by_id)
    monkeypatch.setattr(ResultsRepository, "get_payload_for_version", fake_get_payload)
    monkeypatch.setattr(ResultsRepository, "get_pack_config_for_user_sheet_pack", fake_get_pack_config)
    monkeypatch.setattr(ResultsRepository, "get_latest_pack_config_for_sheet_pack", fake_get_latest_pack_config)
    monkeypatch.setattr(report_storage_service, "download_report_bytes", fake_download_bytes)

    data = asyncio.run(
        get_results_version_payload_by_id(
            _FakeSession(),
            organisation_id=5,
            user_id=1,
            version_id=111,
        )
    )

    assert data is not None
    assert pack_lookup_calls == [99]
    assert data["pack_config"] == {"ID": "UMR", "territory": "UK"}
