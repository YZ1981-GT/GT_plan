"""Import artifact governance.

This service turns upload_token bundles into durable, auditable objects.  The
current storage backend is local filesystem, but callers interact through a
storage_uri so shared-volume/object-store backends can be added without
changing import orchestration.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset_models import ArtifactStatus, ImportArtifact
from app.services.import_artifact_storage import ImportArtifactStorage


class ImportArtifactService:
    @staticmethod
    def _checksum_files(bundle_dir: Path, manifest_files: list[dict[str, Any]]) -> str:
        digest = hashlib.sha256()
        for item in manifest_files:
            stored_name = item.get("stored_name")
            if not stored_name:
                continue
            path = bundle_dir / stored_name
            digest.update(str(stored_name).encode("utf-8"))
            if not path.exists():
                continue
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    async def create_local_bundle_artifact(
        db: AsyncSession,
        *,
        project_id: UUID,
        upload_token: str,
        bundle_dir: Path,
        manifest_files: list[dict[str, Any]],
        total_size_bytes: int,
        expires_at: datetime,
        created_by: UUID | None,
    ) -> ImportArtifact:
        """Create or update the DB record for a shared filesystem upload bundle."""
        return await ImportArtifactService.create_bundle_artifact(
            db,
            project_id=project_id,
            upload_token=upload_token,
            storage_uri=f"sharedfs://{bundle_dir.resolve().as_posix()}",
            bundle_dir=bundle_dir,
            manifest_files=manifest_files,
            total_size_bytes=total_size_bytes,
            expires_at=expires_at,
            created_by=created_by,
        )

    @staticmethod
    async def create_bundle_artifact(
        db: AsyncSession,
        *,
        project_id: UUID,
        upload_token: str,
        storage_uri: str,
        manifest_files: list[dict[str, Any]],
        total_size_bytes: int,
        expires_at: datetime,
        created_by: UUID | None,
        bundle_dir: Path | None = None,
        checksum: str | None = None,
    ) -> ImportArtifact:
        """Create or update the DB record for an upload bundle."""
        if checksum is None and bundle_dir is not None:
            checksum = ImportArtifactService._checksum_files(bundle_dir, manifest_files)
        result = await db.execute(
            sa.select(ImportArtifact).where(ImportArtifact.upload_token == upload_token)
        )
        artifact = result.scalar_one_or_none()
        if artifact is None:
            artifact = ImportArtifact(
                id=uuid4(),
                project_id=project_id,
                upload_token=upload_token,
            )
            db.add(artifact)

        artifact.status = ArtifactStatus.active
        artifact.storage_uri = storage_uri
        artifact.checksum = checksum
        artifact.total_size_bytes = total_size_bytes
        artifact.file_manifest = manifest_files
        artifact.file_count = len(manifest_files)
        artifact.expires_at = expires_at
        artifact.created_by = created_by
        await db.flush()
        return artifact

    @staticmethod
    async def get_by_upload_token(
        db: AsyncSession,
        *,
        project_id: UUID,
        upload_token: str,
    ) -> ImportArtifact | None:
        result = await db.execute(
            sa.select(ImportArtifact).where(
                ImportArtifact.project_id == project_id,
                ImportArtifact.upload_token == upload_token,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_expired(db: AsyncSession, artifact_id: UUID) -> None:
        await db.execute(
            sa.update(ImportArtifact)
            .where(ImportArtifact.id == artifact_id)
            .values(status=ArtifactStatus.expired)
        )

    @staticmethod
    async def mark_consumed(db: AsyncSession, artifact_id: UUID) -> None:
        await db.execute(
            sa.update(ImportArtifact)
            .where(ImportArtifact.id == artifact_id)
            .values(status=ArtifactStatus.consumed)
        )

    @staticmethod
    async def list_artifacts(db: AsyncSession, *, project_id: UUID) -> list[ImportArtifact]:
        result = await db.execute(
            sa.select(ImportArtifact)
            .where(ImportArtifact.project_id == project_id)
            .order_by(ImportArtifact.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def local_path_from_uri(storage_uri: str) -> Path | None:
        """Resolve filesystem-backed artifact URIs.

        `local://` is kept for existing records. New records use `sharedfs://`
        to make the production contract explicit: every worker must see the
        same configured ledger upload root.
        """
        for prefix in ("sharedfs://", "local://"):
            if storage_uri.startswith(prefix):
                return Path(storage_uri[len(prefix):])
        return None

    @staticmethod
    def is_s3_uri(storage_uri: str | None) -> bool:
        return bool(storage_uri and ImportArtifactStorage.parse_s3_uri(storage_uri))

    @staticmethod
    def materialize_bundle(storage_uri: str, *, upload_token: str) -> Path | None:
        local_path = ImportArtifactService.local_path_from_uri(storage_uri)
        if local_path is not None:
            if not local_path.exists():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "导入上传产物不可访问：sharedfs 路径不存在。"
                        "请确认 Web 与 import_worker 挂载同一 LEDGER_UPLOAD_STORAGE_ROOT，或改用 S3 artifact 存储。"
                    ),
                )
            if not (local_path / "manifest.json").exists():
                raise HTTPException(
                    status_code=503,
                    detail="导入上传产物清单缺失：manifest.json 不存在，请重新上传或检查共享存储同步。",
                )
            return local_path
        if ImportArtifactService.is_s3_uri(storage_uri):
            return ImportArtifactStorage.materialize_s3_bundle(storage_uri, upload_token=upload_token)
        return None
