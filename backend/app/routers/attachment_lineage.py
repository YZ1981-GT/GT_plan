"""附件溯源关联 API — wp-traceability-panel Task 2.3

POST /api/attachments/{id}/link — 关联附件到 target_type+target_id+target_ref
GET  /api/attachments/{id}/links — 查询附件的所有关联
DELETE /api/attachments/{id}/link/{link_id} — 删除关联

Requirements: 3.1, 3.2

spec formula-hub-integrity-closure（需求 7.1~7.3，ADR-FHIC-13），三个端点依次：

1. 判定 ``project_id`` 列已就绪（迁移 V227），未就绪返回 503 ``ATTACHMENT_LINEAGE_MIGRATION_PENDING``——先于任何
   触达 ``attachment_lineage`` 的语句（模型映射了该列，ORM 读写都会带上它）；
2. 既有的附件 wp-link 可见性检查（附件绑定了底稿时要求至少一个关联底稿可见，否则 404）；
3. 取附件所属项目（附件不存在或已软删 ⇒ 404），按该项目判定级别：关联与删除关联要求 edit，查询要求 readonly
   （与 ``require_project_access`` 同一实现，不足即 403，判定先于任何写入）；
4. 只读写本项目的关联行：POST 写入附件所属项目；GET / DELETE 只认 ``project_id`` 等于该项目的行，
   ``project_id`` 为空的行（迁移后旧代码写入）对任何项目都不可见，由修复工具回填后才出现。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import assert_project_permission, get_current_user, get_db
from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment
from app.models.core import User
from app.schemas.attachment_lineage_schema import (
    AttachmentLineageCreate,
    AttachmentLineageResponse,
)
from app.services.attachment_lineage_schema import ensure_lineage_project_column
from app.services.wp_visibility.entry_integration import (
    enforce_attachment_wp_visibility,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/attachments",
    tags=["attachment-lineage"],
)


async def _visible_attachment_project(db: AsyncSession, current_user: User, attachment_id: uuid.UUID) -> uuid.UUID:
    """既有的附件 wp-link 可见性检查，再取附件所属项目（附件不存在或已软删 ⇒ 404）。"""
    # Wp_Bound_Gate 附件可见性隔离（Task 4 / R3 leak_risk → gated，additive）：
    # 若附件已绑定底稿，要求当前用户对至少一个关联底稿可见（scope_cycles/委派隔离），
    # 全部不可见 → External_Not_Found(404)；未绑定底稿 → 放行，交调用方的项目级判定。
    await enforce_attachment_wp_visibility(
        db, current_user, attachment_id=attachment_id,
        action="attach_read", method="GET", entrypoint="attachment.read",
    )
    project_id = (await db.execute(
        select(Attachment.project_id).where(Attachment.id == attachment_id, Attachment.is_deleted == false())
    )).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    return project_id


@router.post("/{attachment_id}/link", response_model=AttachmentLineageResponse)
async def link_attachment(
    attachment_id: uuid.UUID,
    body: AttachmentLineageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将附件关联到具体位置（wp_cell / report_row / note_section）；要求附件所属项目 edit。"""
    await ensure_lineage_project_column(db)
    project_id = await _visible_attachment_project(db, current_user, attachment_id)
    await assert_project_permission(db, current_user, project_id, "edit")
    lineage = AttachmentLineage(
        attachment_id=attachment_id,
        project_id=project_id,
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
    """查询附件的所有溯源关联；要求附件所属项目 readonly。"""
    await ensure_lineage_project_column(db)
    project_id = await _visible_attachment_project(db, current_user, attachment_id)
    await assert_project_permission(db, current_user, project_id, "readonly")
    stmt = (
        select(AttachmentLineage)
        .where(AttachmentLineage.attachment_id == attachment_id, AttachmentLineage.project_id == project_id)
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
    """删除附件溯源关联；要求附件所属项目 edit。"""
    await ensure_lineage_project_column(db)
    project_id = await _visible_attachment_project(db, current_user, attachment_id)
    await assert_project_permission(db, current_user, project_id, "edit")
    stmt = select(AttachmentLineage).where(
        AttachmentLineage.id == link_id,
        AttachmentLineage.attachment_id == attachment_id,
        AttachmentLineage.project_id == project_id,
    )
    result = await db.execute(stmt)
    lineage = result.scalar_one_or_none()
    if not lineage:
        raise HTTPException(status_code=404, detail="关联不存在")
    await db.delete(lineage)
    await db.commit()
    return {"message": "关联已删除"}
