"""不可变字节描述的内部服务；不承担领域 ACL，也不提供公开 blob 下载。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_blob_models import AssetBlob

logger = logging.getLogger(__name__)


class AssetBlobReadRejected(RuntimeError):
    """blob 不可读或完整性校验失败；对外调用方不得回显内部路径。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class VerifiedAssetBlob:
    blob_id: UUID
    content: bytes
    canonical_path: Path
    content_hash: str
    byte_size: int
    media_type: str | None


@dataclass(frozen=True)
class ResolvedAttachmentAsset:
    requested_attachment_id: UUID
    root_attachment_id: UUID
    attachment_version_id: UUID
    version_no: int
    blob_id: UUID
    content_hash: str
    byte_size: int
    media_type: str | None
    file_name: str
    verified: VerifiedAssetBlob


class AssetBlobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def available(self) -> bool:
        dialect = self.db.get_bind().dialect.name
        try:
            if dialect == "postgresql":
                return bool((await self.db.execute(sa.text("SELECT to_regclass('public.asset_blobs')"))).scalar())
            if dialect == "sqlite":
                return bool((await self.db.execute(sa.text(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='asset_blobs'"
                ))).scalar())
        except Exception:
            return False
        return False

    async def register_bytes(
        self,
        *,
        storage_type: str,
        storage_key: str,
        content: bytes,
        media_type: str | None,
        actor_user_id: UUID | None = None,
        actor_service_identity_id: UUID | None = None,
        ingress_policy_version: str = "apc-v1",
    ) -> AssetBlob:
        """按 locator 幂等登记；同 locator 字节变化立即拒绝，不静默改历史 blob。"""
        if (actor_user_id is None) == (actor_service_identity_id is None):
            raise RuntimeError("不可变字节登记必须且只能提供一个操作者")
        digest = hashlib.sha256(content).hexdigest()
        existing = (await self.db.execute(
            sa.select(AssetBlob).where(
                AssetBlob.storage_type == storage_type,
                AssetBlob.storage_key == storage_key,
            )
        )).scalar_one_or_none()
        if existing is not None:
            if existing.content_hash != digest or existing.byte_size != len(content):
                raise RuntimeError("同一存储位置的字节已变化，拒绝复用不可变 blob")
            return existing
        row = AssetBlob(
            content_hash=digest,
            byte_size=len(content),
            detected_media_type=media_type,
            storage_type=storage_type,
            storage_key=storage_key,
            ingress_policy_version=ingress_policy_version,
            security_status="accepted",
            actor_type="user" if actor_user_id is not None else "service",
            actor_user_id=actor_user_id,
            actor_service_identity_id=actor_service_identity_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def register_if_enabled(
        self,
        *,
        storage_type: str,
        storage_key: str,
        content: bytes,
        media_type: str | None,
        actor_user_id: UUID | None,
        actor_service_identity_id: UUID | None = None,
        mode_env: str,
        default_mode: str = "shadow",
    ) -> AssetBlob | None:
        """兼容切换：shadow 缺表/主体时降级；blob_only 明确失败。"""
        mode = os.environ.get(mode_env, default_mode).strip().lower()
        mandatory = mode == "blob_only"
        if (actor_user_id is None) == (actor_service_identity_id is None):
            if mandatory:
                raise RuntimeError("不可变字节登记缺少或存在多个操作者")
            return None
        if not await self.available():
            if mandatory:
                raise RuntimeError("asset_blobs 迁移尚未就绪")
            return None
        try:
            async with self.db.begin_nested():
                return await self.register_bytes(
                    storage_type=storage_type,
                    storage_key=storage_key,
                    content=content,
                    media_type=media_type,
                    actor_user_id=actor_user_id,
                    actor_service_identity_id=actor_service_identity_id,
                )
        except Exception:
            if mandatory:
                raise
            logger.warning("asset blob shadow 登记失败", exc_info=True)
            return None

    async def read_verified(
        self,
        blob_id: UUID,
        *,
        allowed_roots: tuple[str | Path, ...] | None = None,
    ) -> VerifiedAssetBlob:
        """读取并逐字节校验 blob；调用方必须先完成领域对象 ACL。"""
        blob = await self.db.get(AssetBlob, blob_id)
        if blob is None:
            raise AssetBlobReadRejected("blob_not_found")
        if blob.security_status != "accepted":
            raise AssetBlobReadRejected("blob_not_accepted")
        if blob.storage_type != "local":
            raise AssetBlobReadRejected("unsupported_storage_type")

        roots = allowed_roots or default_asset_blob_roots()
        path = resolve_within_roots(blob.storage_key, roots)
        if path is None:
            raise AssetBlobReadRejected("outside_trusted_storage_or_missing")
        try:
            content = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            raise AssetBlobReadRejected("storage_unavailable") from exc
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != blob.byte_size or digest != blob.content_hash:
            raise AssetBlobReadRejected("integrity_mismatch")
        return VerifiedAssetBlob(
            blob_id=blob.id,
            content=content,
            canonical_path=path,
            content_hash=digest,
            byte_size=len(content),
            media_type=blob.detected_media_type,
        )

    async def resolve_attachment_asset(
        self,
        attachment_id: UUID,
        *,
        project_id: UUID,
    ) -> ResolvedAttachmentAsset | None:
        """在根锁内把 legacy/root ID 解析到确定版本，并校验对应本地 blob 字节。

        返回 ``None`` 表示该附件尚无可消费的本地不可变版本；完整性异常明确抛出。
        调用方必须先对请求 ID 完成附件领域 ACL。
        """
        from app.models.attachment_models import Attachment
        from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias

        if not await self.available():
            return None

        root_id = attachment_id
        version_id: UUID | None = None
        try:
            async with self.db.begin_nested():
                alias = await self.db.get(LegacyAttachmentAlias, attachment_id)
            if alias is not None:
                root_id = alias.attachment_id
                version_id = alias.attachment_version_id
        except Exception:
            root_id, version_id = attachment_id, None

        attachment = (
            await self.db.execute(
                sa.select(Attachment).where(Attachment.id == root_id).with_for_update()
            )
        ).scalar_one_or_none()
        if (
            attachment is None
            or attachment.project_id != project_id
            or attachment.is_deleted
            or attachment.state != "available"
        ):
            return None
        if version_id is None:
            version_id = attachment.current_version_id
        if version_id is None:
            return None
        version = await self.db.get(AttachmentVersion, version_id)
        if (
            version is None
            or version.attachment_id != attachment.id
            or version.project_id != project_id
            or version.availability != "available"
            or version.blob_id is None
        ):
            return None
        blob_row = await self.db.get(AssetBlob, version.blob_id)
        if blob_row is None:
            raise AssetBlobReadRejected("blob_not_found")
        if blob_row.storage_type != "local":
            return None
        verified = await self.read_verified(version.blob_id)
        if version.content_hash and version.content_hash != verified.content_hash:
            raise AssetBlobReadRejected("version_hash_mismatch")
        if version.byte_size is not None and version.byte_size != verified.byte_size:
            raise AssetBlobReadRejected("version_size_mismatch")
        return ResolvedAttachmentAsset(
            requested_attachment_id=attachment_id,
            root_attachment_id=attachment.id,
            attachment_version_id=version.id,
            version_no=version.version_no,
            blob_id=verified.blob_id,
            content_hash=verified.content_hash,
            byte_size=verified.byte_size,
            media_type=version.media_type or verified.media_type,
            file_name=attachment.file_name,
            verified=verified,
        )

    async def read_current_attachment_blob(
        self,
        attachment_id: UUID,
        *,
        project_id: UUID,
    ) -> VerifiedAssetBlob | None:
        """兼容读取接口；精确 alias/current 解析委托 :meth:`resolve_attachment_asset`。"""
        resolved = await self.resolve_attachment_asset(
            attachment_id,
            project_id=project_id,
        )
        return resolved.verified if resolved is not None else None


def default_asset_blob_roots() -> tuple[Path, ...]:
    """当前受信本地存储域；blob 自身不扩展任何领域读取权限。"""
    from app.services.attachment_storage_resolver import attachment_root
    from app.services.knowledge_upload_service import knowledge_storage_root

    roots = (attachment_root(), knowledge_storage_root())
    unique: list[Path] = []
    for root in roots:
        resolved = Path(root).resolve(strict=False)
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def resolve_within_roots(
    path_value: str | None,
    roots: tuple[str | Path, ...],
) -> Path | None:
    for root in roots:
        resolved = resolve_within_root(path_value, root)
        if resolved is not None:
            return resolved
    return None


def resolve_within_root(path_value: str | None, root: str | Path) -> Path | None:
    """知识/通用资产本地读边界：realpath 后必须位于领域根内且是文件。"""
    if not path_value or "://" in str(path_value):
        return None
    base = Path(root).resolve(strict=False)
    raw = Path(path_value)
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, base / raw]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(base)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None
