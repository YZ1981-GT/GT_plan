"""过程记录与人机协同标注服务 — Phase 10 Task 4.1-4.3

底稿编辑记录、附件双向关联、AI内容人机协同标注。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Log
from app.models.ai_models import AIContent, AIConfirmationStatus

logger = logging.getLogger(__name__)


class ProcessRecordService:
    """底稿编辑过程记录"""

    async def record_workpaper_edit(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_id: UUID,
        user_id: UUID,
        file_version: int,
        change_summary: str | None = None,
    ) -> dict[str, Any]:
        """记录底稿编辑摘要到 logs 表"""
        log_entry = Log(
            user_id=user_id,
            action_type="workpaper_edit",
            object_type="working_paper",
            object_id=wp_id,
            new_value={
                "project_id": str(project_id),
                "file_version": file_version,
                "edited_by": str(user_id),
                "edited_at": datetime.utcnow().isoformat(),
                "change_summary": change_summary or "底稿已更新",
            },
        )
        db.add(log_entry)
        await db.flush()
        return {"log_id": str(log_entry.id), "action": "workpaper_edit"}

    async def get_edit_history(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """获取底稿编辑历史"""
        stmt = (
            sa.select(Log)
            .where(
                Log.object_type == "working_paper",
                Log.object_id == wp_id,
                Log.action_type == "workpaper_edit",
            )
            .order_by(Log.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "action_type": r.action_type,
                "new_value": r.new_value,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


class AttachmentLinkService:
    """附件双向关联"""

    async def get_workpaper_attachments(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_id: UUID,
    ) -> list[dict[str, Any]]:
        """获取底稿关联的附件列表"""
        stmt = sa.text(
            "SELECT a.id, a.file_name, a.file_size, a.file_type, a.created_at "
            "FROM attachments a "
            "WHERE a.reference_type = 'working_paper' "
            "AND a.reference_id = :wp_id "
            "AND a.project_id = :project_id "
            "AND (a.is_deleted = false OR a.is_deleted IS NULL) "
            "ORDER BY a.created_at DESC"
        )
        result = await db.execute(stmt, {"wp_id": str(wp_id), "project_id": str(project_id)})
        rows = result.fetchall()
        return [
            {
                "id": str(r.id),
                "file_name": r.file_name,
                "file_size": r.file_size,
                "file_type": r.file_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def get_attachment_workpapers(
        self,
        db: AsyncSession,
        attachment_id: UUID,
    ) -> list[dict[str, Any]]:
        """获取附件关联的底稿列表"""
        stmt = sa.text(
            "SELECT a.reference_id as wp_id, w.wp_code, w.wp_name "
            "FROM attachments a "
            "LEFT JOIN wp_index w ON w.id = ("
            "  SELECT wp_index_id FROM working_papers WHERE id = a.reference_id LIMIT 1"
            ") "
            "WHERE a.id = :att_id "
            "AND a.reference_type = 'working_paper' "
            "AND (a.is_deleted = false OR a.is_deleted IS NULL)"
        )
        result = await db.execute(stmt, {"att_id": str(attachment_id)})
        rows = result.fetchall()
        return [
            {
                "wp_id": str(r.wp_id) if r.wp_id else None,
                "wp_code": r.wp_code,
                "wp_name": r.wp_name,
            }
            for r in rows
        ]

    async def link_attachment_to_workpaper(
        self,
        db: AsyncSession,
        attachment_id: UUID,
        wp_id: UUID,
    ) -> bool:
        """将附件关联到底稿"""
        await db.execute(
            sa.text(
                "UPDATE attachments SET reference_type = 'working_paper', "
                "reference_id = :wp_id WHERE id = :att_id"
            ),
            {"wp_id": str(wp_id), "att_id": str(attachment_id)},
        )
        await db.flush()
        return True


class AIContentTagService:
    """AI 内容人机协同标注"""

    async def get_pending_ai_content(
        self,
        db: AsyncSession,
        project_id: UUID,
        workpaper_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """获取待确认的 AI 生成内容"""
        conditions = [
            AIContent.project_id == project_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
        ]
        if workpaper_id:
            conditions.append(AIContent.workpaper_id == workpaper_id)

        stmt = (
            sa.select(AIContent)
            .where(*conditions)
            .order_by(AIContent.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "content_type": r.content_type.value if hasattr(r.content_type, "value") else r.content_type,
                "summary": r.summary or (r.content_text[:100] if r.content_text else ""),
                "confirmation_status": r.confirmation_status.value if hasattr(r.confirmation_status, "value") else r.confirmation_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def confirm_ai_content(
        self,
        db: AsyncSession,
        content_id: UUID,
        status: str,
        user_id: UUID,
    ) -> dict[str, Any]:
        """确认/拒绝 AI 生成内容

        status: accepted / modified / rejected
        """
        valid = {"accepted", "modified", "rejected"}
        if status not in valid:
            raise ValueError(f"无效状态: {status}，可选: {valid}")

        stmt = sa.select(AIContent).where(AIContent.id == content_id)
        result = await db.execute(stmt)
        content = result.scalar_one_or_none()
        if not content:
            raise ValueError("AI 内容不存在")

        content.confirmation_status = AIConfirmationStatus(status)
        content.confirmed_by = user_id
        content.confirmed_at = datetime.utcnow()
        await db.flush()

        return {
            "id": str(content.id),
            "confirmation_status": status,
            "confirmed_by": str(user_id),
        }

    async def check_unconfirmed(
        self,
        db: AsyncSession,
        project_id: UUID,
        workpaper_id: UUID,
    ) -> dict[str, Any]:
        """检查底稿是否有未确认的 AI 内容（提交复核前检查）"""
        stmt = (
            sa.select(sa.func.count())
            .select_from(AIContent)
            .where(
                AIContent.project_id == project_id,
                AIContent.workpaper_id == workpaper_id,
                AIContent.confirmation_status == AIConfirmationStatus.pending,
            )
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        return {
            "has_unconfirmed": count > 0,
            "unconfirmed_count": count,
            "can_submit_review": count == 0,
        }
