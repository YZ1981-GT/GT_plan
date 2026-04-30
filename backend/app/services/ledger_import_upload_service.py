from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.services.import_artifact_storage import ImportArtifactStorage

logger = logging.getLogger(__name__)


class LedgerImportUploadService:
    CHUNK_SIZE = 1024 * 1024
    ROOT = Path(settings.LEDGER_UPLOAD_STORAGE_ROOT)
    TTL = timedelta(hours=max(1, settings.LEDGER_UPLOAD_TTL_HOURS))

    @classmethod
    def _project_root(cls, project_id: UUID) -> Path:
        root = cls.ROOT / str(project_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _bundle_dir(cls, project_id: UUID, upload_token: str) -> Path:
        return cls._project_root(project_id) / upload_token

    @classmethod
    def _manifest_path(cls, project_id: UUID, upload_token: str) -> Path:
        return cls._bundle_dir(project_id, upload_token) / "manifest.json"

    @staticmethod
    def _safe_filename(filename: str | None, index: int) -> str:
        safe = Path(filename or "").name.strip()
        if safe:
            return safe
        return f"upload_{index + 1}.bin"

    @classmethod
    def _is_expired(cls, created_at: str | None) -> bool:
        if not created_at:
            return True
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            return True
        return created < datetime.utcnow() - cls.TTL

    @classmethod
    def cleanup_expired_bundles(cls, project_id: UUID) -> None:
        project_root = cls._project_root(project_id)
        for child in project_root.iterdir():
            if not child.is_dir():
                continue
            manifest_path = child / "manifest.json"
            created_at: str | None = None
            try:
                if manifest_path.exists():
                    created_at = json.loads(manifest_path.read_text(encoding="utf-8")).get("created_at")
            except Exception:
                created_at = None
            if cls._is_expired(created_at):
                shutil.rmtree(child, ignore_errors=True)

    @classmethod
    async def create_bundle(
        cls,
        project_id: UUID,
        user_id: str,
        files: list[UploadFile],
    ) -> dict[str, Any]:
        cls.cleanup_expired_bundles(project_id)

        valid_uploads = [upload for upload in files if upload and upload.filename]
        max_file_count = max(1, settings.LEDGER_UPLOAD_MAX_FILE_COUNT)
        if len(valid_uploads) > max_file_count:
            raise HTTPException(status_code=413, detail=f"上传文件数超过限制（最多 {max_file_count} 个）")

        upload_token = uuid4().hex
        bundle_dir = cls._bundle_dir(project_id, upload_token)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        max_bytes = max(1, settings.MAX_UPLOAD_SIZE_MB) * 1024 * 1024
        max_total_bytes = max(1, settings.LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB) * 1024 * 1024

        manifest_files: list[dict[str, Any]] = []
        total_size = 0

        try:
            for index, upload in enumerate(valid_uploads):
                safe_name = cls._safe_filename(upload.filename, index)
                stored_name = f"{index:02d}_{safe_name}"
                target_path = bundle_dir / stored_name

                size = 0
                with target_path.open("wb") as target:
                    while True:
                        chunk = await upload.read(cls.CHUNK_SIZE)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise HTTPException(status_code=413, detail=f"文件过大，超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
                        target.write(chunk)

                try:
                    await upload.close()
                except Exception:
                    pass

                total_size += size
                if total_size > max_total_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"上传总大小超过限制（最大 {settings.LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB}MB）",
                    )
                manifest_files.append({
                    "filename": safe_name,
                    "stored_name": stored_name,
                    "size": size,
                })

            if not manifest_files:
                raise HTTPException(status_code=400, detail="未提供文件")

            manifest = {
                "upload_token": upload_token,
                "project_id": str(project_id),
                "created_by": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "total_size": total_size,
                "files": manifest_files,
            }
            cls._manifest_path(project_id, upload_token).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            storage_uri = f"sharedfs://{bundle_dir.resolve().as_posix()}"
            artifact_files = manifest_files
            if ImportArtifactStorage.is_s3_enabled():
                storage_uri, artifact_files = ImportArtifactStorage.upload_bundle(
                    project_id=project_id,
                    upload_token=upload_token,
                    bundle_dir=bundle_dir,
                    manifest=manifest,
                )

            # Artifact 记录是跨实例 worker 读取上传产物的入口，失败必须阻断提交。
            from app.core.database import async_session
            import uuid as _uuid
            from app.services.import_artifact_service import ImportArtifactService

            async with async_session() as art_db:
                await ImportArtifactService.create_bundle_artifact(
                    art_db,
                    project_id=project_id,
                    upload_token=upload_token,
                    storage_uri=storage_uri,
                    bundle_dir=bundle_dir,
                    manifest_files=artifact_files,
                    total_size_bytes=total_size,
                    expires_at=datetime.utcnow() + timedelta(hours=settings.LEDGER_UPLOAD_TTL_HOURS),
                    created_by=_uuid.UUID(user_id) if user_id else None,
                )
                await art_db.commit()

            return manifest
        except Exception:
            shutil.rmtree(bundle_dir, ignore_errors=True)
            raise

    @classmethod
    def load_manifest(cls, project_id: UUID, upload_token: str) -> dict[str, Any]:
        cls.cleanup_expired_bundles(project_id)
        manifest_path = cls._manifest_path(project_id, upload_token)
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="上传文件已过期或不存在，请重新上传")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"上传清单损坏: {exc}") from exc

        if cls._is_expired(manifest.get("created_at")):
            shutil.rmtree(cls._bundle_dir(project_id, upload_token), ignore_errors=True)
            raise HTTPException(status_code=404, detail="上传文件已过期，请重新上传")
        return manifest

    @classmethod
    def get_bundle_files(cls, project_id: UUID, upload_token: str) -> list[tuple[str, Path]]:
        manifest = cls.load_manifest(project_id, upload_token)
        bundle_dir = cls._bundle_dir(project_id, upload_token)
        return cls._files_from_manifest(bundle_dir, manifest)

    @classmethod
    def get_bundle_files_from_path(cls, bundle_dir: Path) -> list[tuple[str, Path]]:
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="上传产物清单不存在，请重新上传")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"上传清单损坏: {exc}") from exc
        if cls._is_expired(manifest.get("created_at")):
            raise HTTPException(status_code=404, detail="上传文件已过期，请重新上传")
        return cls._files_from_manifest(bundle_dir, manifest)

    @staticmethod
    def _files_from_manifest(bundle_dir: Path, manifest: dict[str, Any]) -> list[tuple[str, Path]]:
        file_entries: list[tuple[str, Path]] = []
        for item in manifest.get("files", []):
            filename = item.get("filename") or item.get("stored_name")
            stored_name = item.get("stored_name")
            if not filename or not stored_name:
                continue
            target = bundle_dir / stored_name
            if not target.exists():
                raise HTTPException(status_code=404, detail=f"上传文件缺失: {filename}")
            file_entries.append((filename, target))
        if not file_entries:
            raise HTTPException(status_code=404, detail="上传文件不存在，请重新上传")
        return file_entries
