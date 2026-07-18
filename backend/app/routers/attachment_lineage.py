"""附件溯源关联 API — wp-traceability-panel Task 2.3

POST /api/attachments/{id}/link — 关联附件到 target_type+target_id+target_ref
GET  /api/attachments/{id}/links — 查询附件的所有关联
DELETE /api/attachments/{id}/link/{link_id} — 删除关联

Requirements: 3.1, 3.2
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.attachment_lineage_model import AttachmentLineage
from app.models.core import User
from app.schemas.attachment_lineage_schema import (
    AttachmentLineageCreate,
    AttachmentLineageResponse,
)
from app.services.wp_visibility.entry_integration import (
    enforce_attachment_wp_visibility,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/attachments",
    tags=["attachment-lineage"],
)


@router.post("/{attachment_id}/link", response_model=AttachmentLineageResponse)
async def link_attachment(
    attachment_id: uuid.UUID,
    body: AttachmentLineageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将附件关联到具体位置（wp_cell / report_row / note_section）。"""
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive）：
    # 若附件已绑定底稿，要求当前用户对至少一个关联底稿可见（scope_cycles/委派隔离），
    # 全部不可见 → External_Not_Found(404)；未绑定底稿 → 放行交既有授权（passthrough）。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    lineage = AttachmentLineage(
        attachment_id=attachment_id,
        target_type=body.target_type,
        target_id=body.target_id,
        target_ref=body.target_ref,
    )
    db.add(lineage)
    await db.flush()
    await db.commit()
    await db.refresh(lineage)
    return lineage


@router.get("/{attachment_id}/links", response_model=list[AttachmentLineageResponse])
async def get_attachment_links(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询附件的所有溯源关联。"""
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive）。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    stmt = (
        select(AttachmentLineage)
        .where(AttachmentLineage.attachment_id == attachment_id)
        .order_by(AttachmentLineage.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.delete("/{attachment_id}/link/{link_id}")
async def unlink_attachment(
    attachment_id: uuid.UUID,
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除附件溯源关联。"""
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive）。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    stmt = select(AttachmentLineage).where(
        AttachmentLineage.id == link_id,
        AttachmentLineage.attachment_id == attachment_id,
    )
    result = await db.execute(stmt)
    lineage = result.scalar_one_or_none()
    if not lineage:
        raise HTTPException(status_code=404, detail="关联不存在")
    await db.delete(lineage)
    await db.commit()
    return {"message": "关联已删除"}
