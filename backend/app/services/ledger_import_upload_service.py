from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.services.import_artifact_storage import ImportArtifactStorage

logger = logging.getLogger(__name__)

#: 旧 bundle（manifest 里没有 `sha256` 字段）在需要单位证据的路径上必须重新上传。
#: 这条常量是「哪些键算证据」的唯一来源，避免各处自己数一遍。
MANIFEST_HASH_KEY = "sha256"


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
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if created.tzinfo is not None:
            created = created.replace(tzinfo=None)
        return created < now_naive - cls.TTL

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
                hasher = hashlib.sha256()
                with target_path.open("wb") as target:
                    while True:
                        chunk = await upload.read(cls.CHUNK_SIZE)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise HTTPException(status_code=413, detail=f"文件过大，超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")
                        if total_size + size > max_total_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=(
                                    "上传总大小超过限制"
                                    f"（最大 {settings.LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB}MB）"
                                ),
                            )
                        hasher.update(chunk)
                        target.write(chunk)

                total_size += size
                manifest_files.append({
                    "filename": safe_name,
                    "stored_name": stored_name,
                    "size": size,
                    # R8/AC-14：逐文件 SHA-256 在**流式落盘时**同时算，
                    # 不在事后重读整个文件（大文件重读会把上传耗时翻倍）。
                    MANIFEST_HASH_KEY: hasher.hexdigest(),
                })

            if not manifest_files:
                raise HTTPException(status_code=400, detail="未提供文件")

            manifest = {
                "upload_token": upload_token,
                "project_id": str(project_id),
                "created_by": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
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

            # Artifact 记录是跨实例 worker 读取上传产物的入口。
            # 预览阶段写入失败不阻断（降级为仅本地文件），导入阶段会重试。
            from app.core.database import async_session
            import uuid as _uuid
            from app.services.import_artifact_service import ImportArtifactService

            try:
                async with async_session() as art_db:
                    await ImportArtifactService.create_bundle_artifact(
                        art_db,
                        project_id=project_id,
                        upload_token=upload_token,
                        storage_uri=storage_uri,
                        bundle_dir=bundle_dir,
                        manifest_files=artifact_files,
                        total_size_bytes=total_size,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.LEDGER_UPLOAD_TTL_HOURS),
                        created_by=_uuid.UUID(user_id) if user_id else None,
                    )
                    await art_db.commit()
            except Exception as artifact_err:
                logger.warning(f"Artifact 记录写入失败（不阻断预览）: {artifact_err}")

            return manifest
        except Exception:
            shutil.rmtree(bundle_dir, ignore_errors=True)
            raise
        finally:
            for upload in valid_uploads:
                try:
                    await upload.close()
                except Exception:
                    pass

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
    def cache_detection_meta(
        cls, project_id: UUID, upload_token: str, total_rows_estimate: int
    ) -> None:
        """detect 阶段把 total_rows_estimate 缓存到 manifest，submit 复用避免重算。

        失败不抛异常（缓存是优化非必需，submit 端点缓存缺失时回退重算）。
        """
        try:
            manifest_path = cls._manifest_path(project_id, upload_token)
            if not manifest_path.exists():
                return
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["total_rows_estimate"] = int(total_rows_estimate)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @classmethod
    def get_cached_total_rows(
        cls, project_id: UUID, upload_token: str
    ) -> int | None:
        """读取 detect 缓存的 total_rows_estimate，无则返回 None。"""
        try:
            manifest = cls.load_manifest(project_id, upload_token)
            val = manifest.get("total_rows_estimate")
            return int(val) if val is not None else None
        except Exception:
            return None

    @classmethod
    def cache_unit_detection(
        cls,
        project_id: UUID,
        upload_token: str,
        unit_detection: dict[str, Any] | None,
    ) -> None:
        """detect 阶段把 `unit_detection` 摘要缓存到 manifest（worker 复用）。

        🔴 为什么必须缓存：worker 侧重新 detect 时用的是 bundle 里的
        **stored_name**（带 `00_` 前缀），而 preview 用的是用户原始文件名 ⇒
        逐 file/sheet 的 label 集合不一致 ⇒ `evidence_digest` 必不同 ⇒
        用户确认过的合同在 submit/claim 时被判 `UNIT_DETECTION_CHANGED`。
        缓存的是 detect 端点算出的那一份摘要本身，逐字段与预览相同。

        失败不抛异常（缓存是优化非必需，worker 侧有「按同一 builder 现算」兜底）。
        """
        if not unit_detection:
            return
        try:
            manifest_path = cls._manifest_path(project_id, upload_token)
            if not manifest_path.exists():
                return
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["unit_detection"] = unit_detection
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

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

    # ── R8/AC-14：不可变 bundle 的单位证据 ─────────────────

    @classmethod
    def load_bundle_unit_evidence(
        cls,
        project_id: UUID,
        upload_token: str,
        *,
        require_hashes: bool = True,
    ) -> tuple[dict[str, tuple[str, int]], dict[str, Any]]:
        """读取 bundle 的逐文件 SHA-256 与 manifest，并**复核磁盘文件**。

        返回 `({文件名: (sha256, size)}, manifest)`。

        `require_hashes=True`（默认）时：

        - 任一文件缺 `sha256` → 400 `UPLOAD_BUNDLE_INTEGRITY_FAILED`
          （旧 bundle，必须重新上传；**不得**用「文件大小相同」冒充证据）；
        - 磁盘文件重算 hash 与 manifest 不符 → 400 同上（bundle 已被改动）。

        `require_hashes=False` 只用于纯展示路径（不参与合同构造）。
        """
        manifest = cls.load_manifest(project_id, upload_token)
        bundle_dir = cls._bundle_dir(project_id, upload_token)
        return cls._bundle_evidence_from(bundle_dir, manifest, require_hashes=require_hashes)

    @classmethod
    def load_bundle_unit_evidence_from_path(
        cls,
        bundle_dir: Path,
        *,
        require_hashes: bool = True,
    ) -> tuple[dict[str, tuple[str, int]], dict[str, Any]]:
        """同 `load_bundle_unit_evidence`，但以 bundle 目录为入口（worker 侧使用）。"""
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail="上传产物清单不存在，请重新上传")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"上传清单损坏: {exc}") from exc
        if cls._is_expired(manifest.get("created_at")):
            raise HTTPException(status_code=404, detail="上传文件已过期，请重新上传")
        return cls._bundle_evidence_from(bundle_dir, manifest, require_hashes=require_hashes)

    @classmethod
    def _bundle_evidence_from(
        cls,
        bundle_dir: Path,
        manifest: dict[str, Any],
        *,
        require_hashes: bool,
    ) -> tuple[dict[str, tuple[str, int]], dict[str, Any]]:
        evidence: dict[str, tuple[str, int]] = {}
        entries = [
            item
            for item in manifest.get("files", [])
            if (item.get("filename") or item.get("stored_name")) and item.get("stored_name")
        ]
        if not entries:
            # 「manifest 里一条可用文件都没有」与「有文件但缺 hash」是**两种**缺陷，
            # 必须各有独立判据：合成一处会让任一被删掉时另一条兜住，变异测不出来。
            raise HTTPException(status_code=404, detail="上传文件不存在，请重新上传")
        for item in entries:
            filename = item.get("filename") or item.get("stored_name")
            stored_name = item.get("stored_name")
            target = bundle_dir / stored_name
            if not target.exists():
                raise HTTPException(status_code=404, detail=f"上传文件缺失: {filename}")
            recorded = item.get(MANIFEST_HASH_KEY)
            if not recorded:
                if require_hashes:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error_code": "UPLOAD_BUNDLE_INTEGRITY_FAILED",
                            "message": "上传产物缺少文件校验摘要（旧版本产物），请重新上传",
                        },
                    )
                continue
            actual = _sha256_file(target)
            if actual != recorded:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "UPLOAD_BUNDLE_INTEGRITY_FAILED",
                        "message": f"上传产物已被改动（{filename}），请重新上传",
                    },
                )
            evidence[filename] = (actual, int(item.get("size") or target.stat().st_size))
        return evidence, manifest

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


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 SHA-256（不把大文件读进内存）。"""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
