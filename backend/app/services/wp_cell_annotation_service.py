"""底稿单元格批注服务 — 创建/回复/解决/按状态查询

Sprint 10 Task 10.1: 复核批注 CRUD
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import CellAnnotation


class CellAnnotationService:
    """单元格批注 CRUD 服务"""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        wp_id: uuid.UUID,
        sheet_name: str,
        row_idx: int,
        col_idx: int,
        content: str,
        author_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> CellAnnotation:
        """创建批注"""
        annotation = CellAnnotation(
            id=uuid.uuid4(),
            project_id=project_id,
            object_type="workpaper",
            object_id=wp_id,
            cell_ref=f"{sheet_name}!R{row_idx}C{col_idx}",
            content=content,
            status="open",
            author_id=author_id,
        )
        db.add(annotation)
        await db.flush()
        return annotation

    @staticmethod
    async def reply(
        db: AsyncSession,
        *,
        annotation_id: uuid.UUID,
        reply_content: str,
        replied_by: uuid.UUID,
    ) -> Optional[CellAnnotation]:
        """回复批注"""
        stmt = select(CellAnnotation).where(CellAnnotation.id == annotation_id)
        result = await db.execute(stmt)
        ann = result.scalar_one_or_none()
        if not ann:
            return None
        ann.status = "replied"
        ann.mentioned_user_ids = {
            "reply_content": reply_content,
            "replied_by": str(replied_by),
            "replied_at": datetime.now(timezone.utc).isoformat(),
        }
        ann.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return ann

    @staticmethod
    async def resolve(
        db: AsyncSession,
        *,
        annotation_id: uuid.UUID,
        resolved_by: uuid.UUID,
    ) -> Optional[CellAnnotation]:
        """解决批注"""
        stmt = select(CellAnnotation).where(CellAnnotation.id == annotation_id)
        result = await db.execute(stmt)
        ann = result.scalar_one_or_none()
        if not ann:
            return None
        ann.status = "resolved"
        ann.mentioned_user_ids = ann.mentioned_user_ids or {}
        ann.mentioned_user_ids["resolved_by"] = str(resolved_by)
        ann.mentioned_user_ids["resolved_at"] = datetime.now(timezone.utc).isoformat()
        ann.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return ann

    @staticmethod
    async def list_by_wp(
        db: AsyncSession,
        *,
        wp_id: uuid.UUID,
        status: Optional[str] = None,
    ) -> list[CellAnnotation]:
        """按底稿查询批注列表，可选状态筛选"""
        conditions = [
            CellAnnotation.object_type == "workpaper",
            CellAnnotation.object_id == wp_id,
            CellAnnotation.is_deleted == False,
        ]
        if status:
            conditions.append(CellAnnotation.status == status)
        stmt = select(CellAnnotation).where(and_(*conditions)).order_by(CellAnnotation.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())
