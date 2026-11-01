"""普通附件 legacy 写入到不可变资产模型的分阶段投影。

M0 关闭；M1 shadow（失败不影响 legacy）；M2 起 mandatory dual-write；M3/M4 读侧以版本/blob 为权威。
历史链必须先由 V106/V107 backfill 建 alias；本服务不臆造缺失的历史版本。
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias
from app.services.asset_blob_service import AssetBlobService

logger = logging.getLogger(__name__)

ASSET_PHASES = ("M0", "M1", "M2", "M3", "M4")


def attachment_asset_phase() -> str:
    value = os.environ.get("ATTACHMENT_ASSET_PHASE", "M1").strip().upper()
    if value not in ASSET_PHASES:
        raise RuntimeError(f"ATTACHMENT_ASSET_PHASE 非法：{value!r}")
    return value


def asset_projection_mandatory() -> bool:
    return attachment_asset_phase() in {"M2", "M3", "M4"}


def asset_blob_read_authoritative() -> bool:
    return attachment_asset_phase() in {"M3", "M4"}


@dataclass(frozen=True)
class AttachmentAssetProjection:
    legacy_attachment_id: UUID
    root_attachment_id: UUID
    attachment_version_id: UUID
    blob_id: UUID
    version_no: int


class AttachmentAssetProjectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.blobs = AssetBlobService(db)

    async def register_storage_blob_if_enabled(
        self,
        *,
        storage_type: str,
        storage_key: str,
        content: bytes,
        media_type: str | None,
        actor_user_id: UUID | None,
        actor_service_identity_id: UUID | None = None,
    ):
        """给已由受信编排器落盘的对象登记 blob；M1 降级，M2 起失败阻断。"""
        phase = attachment_asset_phase()
        if phase == "M0":
            return None
        mandatory = phase in {"M2", "M3", "M4"}
        if (actor_user_id is None) == (actor_service_identity_id is None) or not await self.blobs.available():
            if mandatory:
                raise RuntimeError("附件不可变字节登记前置条件未就绪")
            return None
        try:
            async with self.db.begin_nested():
                return await self.blobs.register_bytes(
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
            logger.warning("attachment blob shadow registration failed", exc_info=True)
            return None

    async def project_if_enabled(
        self,
        *,
        legacy_attachment_id: UUID,
        content: bytes,
        media_type: str | None,
        actor_user_id: UUID | None,
    ) -> AttachmentAssetProjection | None:
        phase = attachment_asset_phase()
        if phase == "M0":
            return None
        mandatory = phase in {"M2", "M3", "M4"}
        if actor_user_id is None:
            if mandatory:
                raise RuntimeError("附件资产投影缺少操作者")
            logger.warning("attachment asset shadow skipped: actor missing")
            return None
        if not await self.blobs.available():
            if mandatory:
                raise RuntimeError("asset_blobs 迁移尚未就绪")
            logger.warning("attachment asset shadow skipped: schema unavailable")
            return None
        try:
            async with self.db.begin_nested():
                return await self._project(
                    legacy_attachment_id=legacy_attachment_id,
                    content=content,
                    media_type=media_type,
                    actor_user_id=actor_user_id,
                )
        except Exception:
            if mandatory:
                raise
            logger.warning(
                "attachment asset shadow projection failed: attachment=%s",
                legacy_attachment_id,
                exc_info=True,
            )
            return None

    async def _project(
        self,
        *,
        legacy_attachment_id: UUID,
        content: bytes,
        media_type: str | None,
        actor_user_id: UUID,
    ) -> AttachmentAssetProjection:
        current = await self.db.get(Attachment, legacy_attachment_id)
        if current is None or current.is_deleted:
            raise RuntimeError("待投影附件不存在")
        if current.audit_year is None:
            raise RuntimeError("附件缺少审计年度，不能建立确定版本")

        existing_alias = await self.db.get(LegacyAttachmentAlias, current.id)
        if existing_alias is not None:
            version = await self.db.get(AttachmentVersion, existing_alias.attachment_version_id)
            if version is None or version.content_hash != hashlib.sha256(content).hexdigest():
                raise RuntimeError("既有附件资产投影与本次字节不一致")
            if version.blob_id is None:
                raise RuntimeError("既有附件版本缺少 blob")
            return AttachmentAssetProjection(
                legacy_attachment_id=current.id,
                root_attachment_id=existing_alias.attachment_id,
                attachment_version_id=version.id,
                blob_id=version.blob_id,
                version_no=version.version_no,
            )

        previous_version_id = None
        if current.previous_version_id is None:
            root_id = current.id
            root = current
            version_no = 1
            resolution_kind = "root"
        else:
            previous_alias = await self.db.get(LegacyAttachmentAlias, current.previous_version_id)
            if previous_alias is None:
                raise RuntimeError("上一 legacy 版本尚未回填 alias，拒绝拆分稳定根")
            root_id = previous_alias.attachment_id
            previous_version_id = previous_alias.attachment_version_id
            root = (
                await self.db.execute(
                    sa.select(Attachment).where(Attachment.id == root_id).with_for_update()
                )
            ).scalar_one_or_none()
            if root is None or root.project_id != current.project_id or root.audit_year != current.audit_year:
                raise RuntimeError("附件稳定根与新版本 scope 不一致")
            max_version = (
                await self.db.execute(
                    sa.select(sa.func.max(AttachmentVersion.version_no)).where(
                        AttachmentVersion.attachment_id == root_id
                    )
                )
            ).scalar_one_or_none()
            if max_version is None:
                raise RuntimeError("上一 alias 指向的稳定根没有版本")
            version_no = int(max_version) + 1
            resolution_kind = "current_version"

        blob = await self.blobs.register_bytes(
            storage_type=current.storage_type,
            storage_key=current.file_path,
            content=content,
            media_type=media_type,
            actor_user_id=actor_user_id,
        )
        version_id = uuid4()
        version = AttachmentVersion(
            id=version_id,
            attachment_id=root_id,
            project_id=current.project_id,
            audit_year=current.audit_year,
            version_no=version_no,
            storage_type=current.storage_type,
            storage_key=current.file_path,
            media_type=media_type or current.file_type,
            byte_size=len(content),
            content_hash=blob.content_hash,
            blob_id=blob.id,
            config_snapshot={
                "projection": {
                    "phase": attachment_asset_phase(),
                    "legacy_attachment_id": str(current.id),
                }
            },
            availability="available",
            previous_version_id=previous_version_id,
            actor_type="user",
            actor_user_id=actor_user_id,
        )
        self.db.add(version)
        await self.db.flush()

        if resolution_kind == "current_version":
            await self.db.execute(
                sa.update(LegacyAttachmentAlias)
                .where(
                    LegacyAttachmentAlias.attachment_id == root_id,
                    LegacyAttachmentAlias.resolution_kind == "current_version",
                )
                .values(resolution_kind="historical_version")
            )
        alias = LegacyAttachmentAlias(
            old_attachment_id=current.id,
            attachment_id=root_id,
            attachment_version_id=version_id,
            project_id=current.project_id,
            audit_year=current.audit_year,
            resolution_kind=resolution_kind,
        )
        self.db.add(alias)
        root.current_version_id = version_id
        await self.db.flush()
        return AttachmentAssetProjection(
            legacy_attachment_id=current.id,
            root_attachment_id=root_id,
            attachment_version_id=version_id,
            blob_id=blob.id,
            version_no=version_no,
        )
