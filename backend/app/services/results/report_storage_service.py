from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from app.config import config


class ReportStorageError(Exception):
    """Base class for report storage failures."""


class ReportStorageConfigurationError(ReportStorageError):
    """Raised when required AWS configuration is missing or invalid."""


class ReportUploadError(ReportStorageError):
    """Raised when report upload to S3 fails."""


class ReportObjectNotFoundError(ReportStorageError):
    """Raised when a report object is not found in S3."""


class ReportDownloadError(ReportStorageError):
    """Raised when report download from S3 fails."""


class ReportPayloadFormatError(ReportStorageError):
    """Raised when report payload JSON is invalid or malformed."""


class ReportDeleteError(ReportStorageError):
    """Raised when report deletion from S3 fails."""


class ReportStorageService:
    """Centralized S3 storage service for saved report worksheet payloads.
    
    In development environments (when S3 is disabled), this service mocks
    S3 operations and does not persist payloads. Set ENABLE_S3_DEVELOPMENT=true
    and provide AWS credentials to enable real S3 operations in development.
    """

    def __init__(self) -> None:
        self.bucket_name = os.getenv("REPORT_STORAGE_BUCKET", "bordereaux-report")
        self.region_name = os.getenv("AWS_REGION", "eu-west-2")
        self._client = None
        self._s3_enabled = config.s3_enabled
        self._mock_storage: dict[str, bytes] = {}  # In-memory mock storage for development

    @staticmethod
    def _normalize_organisation_segment(organisation_name: str | None) -> str:
        """Return a safe S3 key segment for organisation name."""
        normalized = str(organisation_name or "").strip()
        if not normalized:
            return "unknown-organisation"
        return normalized.replace("/", "-").replace("\\", "-")

    def generate_s3_key(self, *, organisation_name: str, report_id: int, file_extension: str = "xlsx") -> str:
        """Return S3 object key for a saved worksheet payload."""
        organization_segment = self._normalize_organisation_segment(organisation_name)
        extension = str(file_extension or "xlsx").strip().lower().lstrip(".") or "xlsx"
        return f"{organization_segment}/{int(report_id)}.{extension}"

    def _get_client(self):
        """Initialize and cache S3 client.
        
        In development with S3 disabled, returns None (mock mode).
        In production/staging or development with S3 enabled, initializes boto3 client.
        """
        if not self._s3_enabled:
            return None

        if self._client is not None:
            return self._client

        access_key = config.aws_access_key
        secret_access_key = config.aws_secret_access_key

        if not access_key or not secret_access_key:
            raise ReportStorageConfigurationError(
                "Missing AWS credentials for report storage (AWS_ACCESS_KEY/AWS_SECRET_ACCESS_KEY)"
            )

        try:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_access_key,
                region_name=self.region_name,
            )
        except Exception as exc:
            raise ReportStorageConfigurationError("Failed to initialize S3 client") from exc

        return self._client

    async def upload_report_bytes(
        self,
        *,
        s3_key: str,
        body: bytes,
        content_type: str,
    ) -> None:
        """Upload a binary payload to S3.
        
        In development with S3 disabled, stores in-memory mock.
        In production/staging or development with S3 enabled, uploads to S3.
        """
        if not self._s3_enabled:
            # Mock S3 storage for development
            self._mock_storage[s3_key] = body
            return

        def _upload() -> None:
            client = self._get_client()
            client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=body,
                ContentType=content_type,
            )

        try:
            await asyncio.to_thread(_upload)
        except (NoCredentialsError, ReportStorageConfigurationError) as exc:
            raise ReportStorageConfigurationError("AWS credentials/configuration error during report upload") from exc
        except (ClientError, BotoCoreError) as exc:
            raise ReportUploadError(f"Failed to upload report to S3 key '{s3_key}'") from exc
        except Exception as exc:
            raise ReportUploadError(f"Unexpected failure uploading report to S3 key '{s3_key}'") from exc

    async def upload_report(self, *, s3_key: str, payload: dict[str, Any]) -> None:
        """Upload worksheet payload JSON to S3."""
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        await self.upload_report_bytes(
            s3_key=s3_key,
            body=body,
            content_type="application/json",
        )

    async def download_report_bytes(self, *, s3_key: str) -> bytes:
        """Download raw report payload bytes from S3.
        
        In development with S3 disabled, retrieves from in-memory mock.
        In production/staging or development with S3 enabled, downloads from S3.
        """
        if not self._s3_enabled:
            # Retrieve from mock storage
            if s3_key not in self._mock_storage:
                raise ReportObjectNotFoundError(f"Report object not found for key '{s3_key}' (mock storage)")
            return self._mock_storage[s3_key]

        def _download() -> bytes:
            client = self._get_client()
            response = client.get_object(Bucket=self.bucket_name, Key=s3_key)
            body = response.get("Body")
            if body is None:
                raise ReportDownloadError(f"S3 object body missing for key '{s3_key}'")
            return body.read()

        try:
            return await asyncio.to_thread(_download)
        except (NoCredentialsError, ReportStorageConfigurationError) as exc:
            raise ReportStorageConfigurationError("AWS credentials/configuration error during report download") from exc
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", "")).strip()
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                raise ReportObjectNotFoundError(f"Report object not found for key '{s3_key}'") from exc
            raise ReportDownloadError(f"Failed to download report from S3 key '{s3_key}'") from exc
        except BotoCoreError as exc:
            raise ReportDownloadError(f"Failed to download report from S3 key '{s3_key}'") from exc
        except ReportDownloadError:
            raise
        except Exception as exc:
            raise ReportDownloadError(f"Unexpected failure downloading report from S3 key '{s3_key}'") from exc

    async def download_report(self, *, s3_key: str) -> dict[str, Any]:
        """Download and deserialize worksheet payload JSON from S3."""
        raw = await self.download_report_bytes(s3_key=s3_key)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ReportPayloadFormatError(f"Invalid JSON payload stored at S3 key '{s3_key}'") from exc

        if not isinstance(payload, dict):
            raise ReportPayloadFormatError(f"Expected JSON object payload at S3 key '{s3_key}'")

        return payload

    async def delete_report(self, *, s3_key: str) -> None:
        """Delete worksheet payload object from S3.
        
        In development with S3 disabled, removes from in-memory mock.
        In production/staging or development with S3 enabled, deletes from S3.
        """
        if not self._s3_enabled:
            # Remove from mock storage (no error if not found, like S3)
            self._mock_storage.pop(s3_key, None)
            return

        def _delete() -> None:
            client = self._get_client()
            client.delete_object(Bucket=self.bucket_name, Key=s3_key)

        try:
            await asyncio.to_thread(_delete)
        except (NoCredentialsError, ReportStorageConfigurationError) as exc:
            raise ReportStorageConfigurationError("AWS credentials/configuration error during report delete") from exc
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", "")).strip()
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                raise ReportObjectNotFoundError(f"Report object not found for key '{s3_key}'") from exc
            raise ReportDeleteError(f"Failed to delete report in S3 key '{s3_key}'") from exc
        except BotoCoreError as exc:
            raise ReportDeleteError(f"Failed to delete report in S3 key '{s3_key}'") from exc
        except Exception as exc:
            raise ReportDeleteError(f"Unexpected failure deleting report in S3 key '{s3_key}'") from exc


report_storage_service = ReportStorageService()
