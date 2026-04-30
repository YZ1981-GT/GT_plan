"""Storage helpers for ledger import artifacts.

Local/sharedfs remains the default. S3-compatible storage is enabled only when
``LEDGER_ARTIFACT_STORAGE_BACKEND=s3`` so existing development flows keep
working without object-store credentials.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException

from app.core.config import settings


class ArtifactStorageError(RuntimeError):
    """Raised when the configured artifact storage backend cannot be used."""


@dataclass(frozen=True)
class S3Location:
    bucket: str
    prefix: str


class ImportArtifactStorage:
    """Backend-neutral operations for import upload bundles."""

    @staticmethod
    def backend() -> str:
        return (settings.LEDGER_ARTIFACT_STORAGE_BACKEND or "local").strip().lower()

    @classmethod
    def is_s3_enabled(cls) -> bool:
        return cls.backend() == "s3"

    @staticmethod
    def _failure_mode() -> str:
        return (settings.LEDGER_ARTIFACT_STORAGE_FAILURE_MODE or "").strip().lower()

    @classmethod
    def _guard_read(cls) -> None:
        mode = cls._failure_mode()
        if mode == "timeout":
            raise TimeoutError("artifact storage timeout injected by configuration")
        if mode == "unavailable":
            raise ArtifactStorageError("artifact storage unavailable injected by configuration")

    @classmethod
    def _guard_write(cls) -> None:
        mode = cls._failure_mode()
        if mode == "readonly":
            raise ArtifactStorageError("artifact storage readonly injected by configuration")
        cls._guard_read()

    @staticmethod
    def _normalized_prefix() -> str:
        return (settings.LEDGER_ARTIFACT_S3_PREFIX or "ledger-import").strip().strip("/")

    @classmethod
    def s3_prefix(cls, project_id: UUID, upload_token: str) -> str:
        base = cls._normalized_prefix()
        suffix = f"{project_id}/{upload_token}"
        return f"{base}/{suffix}" if base else suffix

    @classmethod
    def s3_uri(cls, project_id: UUID, upload_token: str) -> str:
        bucket = settings.LEDGER_ARTIFACT_S3_BUCKET.strip()
        if not bucket:
            raise ArtifactStorageError("LEDGER_ARTIFACT_S3_BUCKET is required when S3 storage is enabled")
        return f"s3://{bucket}/{cls.s3_prefix(project_id, upload_token)}"

    @staticmethod
    def parse_s3_uri(storage_uri: str) -> S3Location | None:
        parsed = urlparse(storage_uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            return None
        return S3Location(bucket=parsed.netloc, prefix=parsed.path.lstrip("/").rstrip("/"))

    @classmethod
    def _client(cls):
        cls._guard_read()
        try:
            import boto3
        except ImportError as exc:
            raise ArtifactStorageError("boto3 is required for S3 artifact storage") from exc

        kwargs = {
            "service_name": "s3",
            "region_name": settings.LEDGER_ARTIFACT_S3_REGION or None,
            "use_ssl": settings.LEDGER_ARTIFACT_S3_USE_SSL,
        }
        if settings.LEDGER_ARTIFACT_S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.LEDGER_ARTIFACT_S3_ENDPOINT_URL
        if settings.LEDGER_ARTIFACT_S3_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = settings.LEDGER_ARTIFACT_S3_ACCESS_KEY_ID
        if settings.LEDGER_ARTIFACT_S3_SECRET_ACCESS_KEY:
            kwargs["aws_secret_access_key"] = settings.LEDGER_ARTIFACT_S3_SECRET_ACCESS_KEY
        return boto3.client(**kwargs)

    @classmethod
    def upload_bundle(
        cls,
        *,
        project_id: UUID,
        upload_token: str,
        bundle_dir: Path,
        manifest: dict,
    ) -> tuple[str, list[dict]]:
        """Upload a local bundle directory to S3 and return storage URI/manifest."""
        if not cls.is_s3_enabled():
            raise ArtifactStorageError("S3 storage is not enabled")
        cls._guard_write()
        location = cls.parse_s3_uri(cls.s3_uri(project_id, upload_token))
        if location is None:
            raise ArtifactStorageError("invalid generated S3 URI")

        client = cls._client()
        updated_files: list[dict] = []
        for item in manifest.get("files", []):
            stored_name = item.get("stored_name")
            if not stored_name:
                continue
            path = bundle_dir / stored_name
            key = f"{location.prefix}/{stored_name}"
            client.upload_file(str(path), location.bucket, key)
            updated = dict(item)
            updated["object_key"] = key
            updated_files.append(updated)

        manifest_key = f"{location.prefix}/manifest.json"
        object_manifest = {**manifest, "files": updated_files, "storage_backend": "s3"}
        client.put_object(
            Bucket=location.bucket,
            Key=manifest_key,
            Body=json.dumps(object_manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        return f"s3://{location.bucket}/{location.prefix}", updated_files

    @classmethod
    def materialize_s3_bundle(cls, storage_uri: str, *, upload_token: str) -> Path:
        """Download an S3 bundle to a local worker cache directory."""
        location = cls.parse_s3_uri(storage_uri)
        if location is None:
            raise HTTPException(status_code=500, detail=f"不支持的对象存储 URI: {storage_uri}")
        cls._guard_read()
        client = cls._client()
        target_dir = Path(settings.LEDGER_ARTIFACT_DOWNLOAD_ROOT) / upload_token
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest_key = f"{location.prefix}/manifest.json"
        manifest_path = target_dir / "manifest.json"
        try:
            response = client.get_object(Bucket=location.bucket, Key=manifest_key)
            manifest = json.loads(response["Body"].read().decode("utf-8"))
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            for item in manifest.get("files", []):
                stored_name = item.get("stored_name")
                object_key = item.get("object_key") or (f"{location.prefix}/{stored_name}" if stored_name else None)
                if not stored_name or not object_key:
                    continue
                client.download_file(location.bucket, object_key, str(target_dir / stored_name))
        except Exception as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise HTTPException(status_code=503, detail=f"对象存储产物读取失败: {exc}") from exc
        return target_dir
