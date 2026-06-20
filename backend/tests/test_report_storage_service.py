from __future__ import annotations

import asyncio

from botocore.exceptions import ClientError

from app.services.results.report_storage_service import (
    ReportObjectNotFoundError,
    ReportPayloadFormatError,
    ReportStorageService,
)


class _FakeBody:
    def __init__(self, content: bytes):
        self._content = content

    def read(self) -> bytes:
        return self._content


class _FakeClient:
    def __init__(self):
        self.put_calls: list[dict[str, object]] = []
        self.get_payload: bytes | None = None

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs):
        if self.get_payload is None:
            raise RuntimeError("missing payload")
        return {"Body": _FakeBody(self.get_payload)}


def test_generate_s3_key_uses_expected_structure():
    service = ReportStorageService()

    key = service.generate_s3_key(organisation_name="acme", report_id=789)

    assert key == "acme/789.xlsx"


def test_generate_s3_key_sanitizes_organisation_name_path_separators():
    service = ReportStorageService()

    key = service.generate_s3_key(organisation_name="Acme/UK", report_id=10)

    assert key == "Acme-UK/10.xlsx"


def test_generate_s3_key_supports_custom_extension():
    service = ReportStorageService()

    key = service.generate_s3_key(organisation_name="acme", report_id=11, file_extension="json")

    assert key == "acme/11.json"


def test_upload_report_writes_json_payload(monkeypatch):
    fake_client = _FakeClient()
    service = ReportStorageService()
    monkeypatch.setattr(service, "_get_client", lambda: fake_client)

    asyncio.run(
        service.upload_report(
            s3_key="1/2/3.json",
            payload={"mapped_headers": {"A": "B"}, "saved_data": [{"id": 1}]},
        )
    )

    assert len(fake_client.put_calls) == 1
    call = fake_client.put_calls[0]
    assert call["Bucket"] == service.bucket_name
    assert call["Key"] == "1/2/3.json"
    assert call["ContentType"] == "application/json"


def test_upload_report_bytes_writes_binary_payload(monkeypatch):
    fake_client = _FakeClient()
    service = ReportStorageService()
    monkeypatch.setattr(service, "_get_client", lambda: fake_client)

    asyncio.run(
        service.upload_report_bytes(
            s3_key="acme/101.xlsx",
            body=b"binary-data",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    )

    assert len(fake_client.put_calls) == 1
    call = fake_client.put_calls[0]
    assert call["Key"] == "acme/101.xlsx"
    assert call["ContentType"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_download_report_bytes_returns_raw_payload(monkeypatch):
    fake_client = _FakeClient()
    fake_client.get_payload = b"excel-binary"
    service = ReportStorageService()
    monkeypatch.setattr(service, "_get_client", lambda: fake_client)

    payload = asyncio.run(service.download_report_bytes(s3_key="acme/101.xlsx"))

    assert payload == b"excel-binary"


def test_download_report_raises_for_missing_object(monkeypatch):
    service = ReportStorageService()

    class _MissingObjectClient:
        def get_object(self, **_kwargs):
            raise ClientError(
                error_response={"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                operation_name="GetObject",
            )

    monkeypatch.setattr(service, "_get_client", lambda: _MissingObjectClient())

    try:
        asyncio.run(service.download_report(s3_key="1/2/3.json"))
        raise AssertionError("Expected ReportObjectNotFoundError")
    except ReportObjectNotFoundError:
        pass


def test_download_report_raises_for_invalid_json(monkeypatch):
    fake_client = _FakeClient()
    fake_client.get_payload = b"not json"
    service = ReportStorageService()
    monkeypatch.setattr(service, "_get_client", lambda: fake_client)

    try:
        asyncio.run(service.download_report(s3_key="1/2/3.json"))
        raise AssertionError("Expected ReportPayloadFormatError")
    except ReportPayloadFormatError:
        pass
