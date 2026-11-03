"""AI run 对项目附件的显式授权、版本钉住与可信正文加载。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_blob_models import AiChatRunResource
from app.models.attachment_models import Attachment
from app.models.evidence_governance_models import AttachmentVersion
from app.services.asset_blob_service import (
    AssetBlobReadRejected,
    AssetBlobService,
    ResolvedAttachmentAsset,
)


def project_attachment_input_enabled() -> bool:
    return os.environ.get("AI_PROJECT_ATTACHMENT_INPUT", "true").strip().lower() in {
        "1", "true", "yes", "on",
    }


@dataclass(frozen=True)
class AuthorizedProjectAttachment:
    requested_id: UUID
    asset: ResolvedAttachmentAsset


@dataclass(frozen=True)
class ProjectAttachmentContextItem:
    id: UUID
    label: str
    content: str | None
    version: str
    status: str
    reason: str = ""


class AiRunResourceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.assets = AssetBlobService(db)

    async def _resource_table_available(self) -> bool:
        dialect = self.db.get_bind().dialect.name
        try:
            if dialect == "postgresql":
                return bool((await self.db.execute(
                    sa.text("SELECT to_regclass('public.ai_chat_run_resources')")
                )).scalar())
            if dialect == "sqlite":
                return bool((await self.db.execute(sa.text(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_chat_run_resources'"
                ))).scalar())
        except Exception:
            return False
        return False

    async def authorize_project_attachments(
        self,
        *,
        user: Any,
        host: Any,
        attachment_ids: list[UUID],
    ) -> list[AuthorizedProjectAttachment]:
        """逐项按目标项目与关联底稿可见性授权，并在根锁下解析确定版本。"""
        if not attachment_ids:
            return []
        if not project_attachment_input_enabled():
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "AI_PROJECT_ATTACHMENT_INPUT_DISABLED",
                    "message": "项目附件加入 AI 对话功能尚未启用",
                },
            )
        project_id = getattr(host, "project_id", None)
        if project_id is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "PROJECT_ATTACHMENT_REQUIRES_PROJECT_HOST",
                    "message": "全局对话不能引用项目附件",
                },
            )
        if not await self._resource_table_available():
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": "AI_RUN_RESOURCE_SCHEMA_NOT_READY",
                    "message": "AI 附件资源迁移尚未就绪，请联系管理员",
                },
            )

        from app.services.attachment_access import require_attachment_permission
        from app.services.wp_visibility.entry_integration import enforce_attachment_wp_visibility

        pins: list[AuthorizedProjectAttachment] = []
        for attachment_id in attachment_ids:
            attachment = await require_attachment_permission(
                self.db, user, attachment_id, "readonly",
            )
            if attachment.project_id != project_id:
                raise HTTPException(status_code=404, detail="附件不存在或无权访问")
            await enforce_attachment_wp_visibility(
                self.db,
                user,
                attachment_id=attachment_id,
                action="attach_read",
                method="POST",
                entrypoint="ai_chat.project_attachment",
            )
            try:
                asset = await self.assets.resolve_attachment_asset(
                    attachment_id,
                    project_id=project_id,
                )
            except AssetBlobReadRejected as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "PROJECT_ATTACHMENT_INTEGRITY_FAILED",
                        "message": "项目附件完整性校验失败，不能加入 AI 对话",
                    },
                ) from exc
            if asset is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": "PROJECT_ATTACHMENT_VERSION_NOT_READY",
                        "message": "项目附件尚无可用的不可变版本，不能加入 AI 对话",
                    },
                )
            pins.append(AuthorizedProjectAttachment(attachment_id, asset))
        return pins

    async def persist_chat_attachments(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        attachments: list[Any],
    ) -> None:
        """记录本 run 实际获准的会话上传附件及其原始字节摘要。"""
        for attachment in attachments:
            self.db.add(AiChatRunResource(
                run_id=run_id,
                session_id=session_id,
                resource_kind="chat_upload",
                resource_id=attachment.id,
                attachment_version_id=None,
                blob_id=None,
                content_hash=attachment.sha256,
                actor_user_id=actor_user_id,
            ))
        if attachments:
            await self.db.flush()

    async def persist_project_attachments(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        pins: list[AuthorizedProjectAttachment],
    ) -> None:
        """把已授权的确定版本写入 run 桥表。只 flush，由 run 路由统一 commit。"""
        for pin in pins:
            asset = pin.asset
            self.db.add(AiChatRunResource(
                run_id=run_id,
                session_id=session_id,
                resource_kind="project_attachment",
                resource_id=pin.requested_id,
                attachment_version_id=asset.attachment_version_id,
                blob_id=asset.blob_id,
                content_hash=asset.content_hash,
                actor_user_id=actor_user_id,
            ))
        if pins:
            await self.db.flush()

    async def load_project_attachment_context(
        self,
        *,
        run_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        project_id: UUID | None,
        requested_ids: list[UUID],
    ) -> list[ProjectAttachmentContextItem]:
        """按 run 桥表读取钉住的版本，重新验 hash 后从该版本字节提取正文。"""
        if not requested_ids:
            return []
        if project_id is None:
            raise RuntimeError("项目附件上下文缺少项目 scope")
        rows = list((await self.db.execute(
            sa.select(AiChatRunResource).where(
                AiChatRunResource.run_id == run_id,
                AiChatRunResource.session_id == session_id,
                AiChatRunResource.actor_user_id == actor_user_id,
                AiChatRunResource.resource_kind == "project_attachment",
            )
        )).scalars().all())
        by_requested = {row.resource_id: row for row in rows}
        missing = [item for item in requested_ids if item not in by_requested]
        if missing:
            raise RuntimeError("AI run 的项目附件版本钉住记录不完整")

        out: list[ProjectAttachmentContextItem] = []
        seen_versions: set[UUID] = set()
        for requested_id in requested_ids:
            row = by_requested[requested_id]
            if row.attachment_version_id is None or row.blob_id is None or not row.content_hash:
                raise RuntimeError("AI run 项目附件记录缺少 version/blob/hash")
            version = await self.db.get(AttachmentVersion, row.attachment_version_id)
            if (
                version is None
                or version.project_id != project_id
                or version.blob_id != row.blob_id
                or version.content_hash != row.content_hash
                or version.availability != "available"
            ):
                raise RuntimeError("AI run 项目附件版本与钉住记录不一致")
            verified = await self.assets.read_verified(row.blob_id)
            if verified.content_hash != row.content_hash:
                raise RuntimeError("AI run 项目附件字节与钉住 hash 不一致")
            requested = await self.db.get(Attachment, requested_id)
            root = await self.db.get(Attachment, version.attachment_id)
            label = (
                requested.file_name if requested is not None
                else (root.file_name if root is not None else str(requested_id))
            )
            if version.id in seen_versions:
                out.append(ProjectAttachmentContextItem(
                    id=requested_id,
                    label=label,
                    content=None,
                    version=str(version.version_no),
                    status="unavailable",
                    reason="duplicate_version",
                ))
                continue
            seen_versions.add(version.id)
            content = await _extract_attachment_text(
                verified.content,
                label,
                str(verified.canonical_path),
            )
            out.append(ProjectAttachmentContextItem(
                id=requested_id,
                label=label,
                content=content,
                version=str(version.version_no),
                status="included" if content else "unavailable",
                reason="" if content else "no_extractable_text",
            ))
        return out


async def _extract_attachment_text(content: bytes, file_name: str, file_path: str) -> str | None:
    """只从钉住字节提取正文，绝不回退 Attachment.ocr_text 可变镜像。"""
    from app.services.knowledge_folder_service import (
        CONTENT_TEXT_MAX_CHARS,
        PLAIN_TEXT_EXTENSIONS,
        decode_text_bytes,
    )

    suffix = Path(file_name).suffix.lower()
    if suffix in PLAIN_TEXT_EXTENSIONS:
        text = decode_text_bytes(content)
        return text[:CONTENT_TEXT_MAX_CHARS] if text.strip() else None
    from app.services.knowledge_upload_service import extract_text_with_ocr

    text = await extract_text_with_ocr(file_path, content, file_name.lower())
    return text[:CONTENT_TEXT_MAX_CHARS] if text and text.strip() else None
