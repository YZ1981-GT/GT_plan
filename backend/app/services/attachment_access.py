"""按附件真实所属项目判权限（spec attachment-security-baseline 需求 2.3、3、4.1、4.2）。

附件端点的路径只有附件 id。先取附件（不存在 / 已软删 ⇒ 404），再按附件**所属项目**走
``assert_project_permission``（与 ``require_project_access`` 同一实现：admin 放行；非 readonly 级判归档 ⇒ 423）。

改造前删除 / 回滚端点挂的是 ``require_project_access("edit")``：附件路径里没有项目，FastAPI 便把 ``project_id``
当成必填查询参数，调用方传哪个项目就按哪个判；附件端点自写的成员判定也不判归档。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import assert_project_permission
from app.models.attachment_models import Attachment
from app.models.core import User


async def load_attachment(db: AsyncSession, attachment_id: UUID, *, include_deleted: bool = False) -> Attachment:
    stmt = sa.select(Attachment).where(Attachment.id == attachment_id)
    if not include_deleted:
        stmt = stmt.where(Attachment.is_deleted == sa.false())
    att = (await db.execute(stmt)).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    return att


async def require_attachment_permission(
    db: AsyncSession, user: User, attachment_id: UUID, min_permission: str, *, include_deleted: bool = False,
) -> Attachment:
    """取附件并要求当前用户在其所属项目至少 ``min_permission``。"""
    att = await load_attachment(db, attachment_id, include_deleted=include_deleted)
    await assert_project_permission(db, user, att.project_id, min_permission)
    return att
