"""单元格级复核批注服务 — Phase 10 Task 15.1"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10_models import CellAnnotation

logger = logging.getLogger(__name__)


class AnnotationService:
    """单元格批注 CRUD + 穿透关联"""

    async def create_annotation(
        self,
        db: AsyncSession,
        project_id: UUID,
        author_id: UUID,
        object_type: str,
        object_id: UUID,
        content: str,
        cell_ref: str | None = None,
        priority: str = "medium",
        mentioned_user_ids: list[UUID] | None = None,
    ) -> dict[str, Any]:
        ann = CellAnnotation(
            project_id=project_id,
            author_id=author_id,
            object_type=object_type,
            object_id=object_id,
            cell_ref=cell_ref,
            content=content,
            priority=priority,
            mentioned_user_ids=[str(u) for u in mentioned_user_ids] if mentioned_user_ids else None,
        )
        db.add(ann)
        await db.flush()
        return self._to_dict(ann)

    async def list_annotations(
        self,
        db: AsyncSession,
        project_id: UUID,
        object_type: str | None = None,
        object_id: UUID | None = None,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = [
            CellAnnotation.project_id == project_id,
            CellAnnotation.is_deleted == sa.false(),
        ]
        if object_type:
            conditions.append(CellAnnotation.object_type == object_type)
        if object_id:
            conditions.append(CellAnnotation.object_id == object_id)
        if status:
            conditions.append(CellAnnotation.status == status)
        if priority:
            conditions.append(CellAnnotation.priority == priority)

        stmt = (
            sa.select(CellAnnotation)
            .where(*conditions)
            .order_by(CellAnnotation.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [self._to_dict(a) for a in result.scalars().all()]

    async def update_annotation(
        self,
        db: AsyncSession,
        annotation_id: UUID,
        status: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        ann = await db.get(CellAnnotation, annotation_id)
        if not ann:
            raise ValueError("批注不存在")
        if status:
            valid = {"pending", "replied", "resolved"}
            if status not in valid:
                raise ValueError(f"无效状态: {status}")
            ann.status = status
        if content:
            ann.content = content
        ann.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return self._to_dict(ann)

    async def link_to_conversation(
        self,
        db: AsyncSession,
        annotation_id: UUID,
        conversation_id: UUID,
    ) -> dict[str, Any]:
        """批注升级为对话"""
        ann = await db.get(CellAnnotation, annotation_id)
        if not ann:
            raise ValueError("批注不存在")
        ann.conversation_id = conversation_id
        await db.flush()
        return self._to_dict(ann)

    async def create_linked_annotation(
        self,
        db: AsyncSession,
        source_annotation_id: UUID,
        project_id: UUID,
        author_id: UUID,
        target_object_type: str,
        target_object_id: UUID,
        target_cell_ref: str | None = None,
    ) -> dict[str, Any]:
        """穿透关联：附注批注→底稿批注"""
        source = await db.get(CellAnnotation, source_annotation_id)
        if not source:
            raise ValueError("源批注不存在")
        linked = CellAnnotation(
            project_id=project_id,
            author_id=author_id,
            object_type=target_object_type,
            object_id=target_object_id,
            cell_ref=target_cell_ref,
            content=f"[关联批注] {source.content}",
            priority=source.priority,
            linked_annotation_id=source_annotation_id,
        )
        db.add(linked)
        await db.flush()
        return self._to_dict(linked)

    def _to_dict(self, a: CellAnnotation) -> dict[str, Any]:
        return {
            "id": str(a.id),
            "project_id": str(a.project_id),
            "object_type": a.object_type,
            "object_id": str(a.object_id),
            "cell_ref": a.cell_ref,
            "content": a.content,
            "priority": a.priority,
            "status": a.status,
            "author_id": str(a.author_id),
            "mentioned_user_ids": a.mentioned_user_ids,
            "linked_annotation_id": str(a.linked_annotation_id) if a.linked_annotation_id else None,
            "conversation_id": str(a.conversation_id) if a.conversation_id else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
