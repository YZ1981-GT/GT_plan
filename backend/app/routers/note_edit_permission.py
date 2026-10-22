"""附注编辑权限判定查询 — partner-manager-edit-permission §4.10

GET /api/projects/{project_id}/disclosure-notes/edit-permission

自身 readonly 级鉴权（``require_project_access("readonly")``）：
- readonly 跳过归档守卫 ⇒ 已归档项目返回「不能编辑 + 归档原因」而非 423。
- 非成员 → 403「权限不足」（前端视同不能编辑）。

判定走 ``assert_note_edit_access(consol_lock=False)``（合并锁不参与，需求 10.1）；
``is_eqcr`` 一律给出；其他异常冒泡为失败响应，不返回「能编辑」。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.eqcr_resolver import is_project_eqcr
from app.services.note_edit_gate import assert_note_edit_access, note_edit_rejection_reason

router = APIRouter(
    prefix="/api/projects/{project_id}/disclosure-notes",
    tags=["note-edit-permission"],
)


@router.get("/edit-permission")
async def get_note_edit_permission(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """附注编辑权限判定查询：返回当前用户能否编辑该项目附注及原因。

    不修改任何业务数据。``is_eqcr`` 一律给出（需求 10.1）。
    已归档项目返回「不能编辑 + 归档原因」（readonly 鉴权跳过归档守卫）。
    """
    is_eqcr = await is_project_eqcr(db, current_user, project_id)
    try:
        await assert_note_edit_access(db, current_user, project_id, consol_lock=False)
    except HTTPException as exc:
        if exc.status_code in (403, 423):
            return {
                "can_edit": False,
                "reason": note_edit_rejection_reason(exc),
                "is_eqcr": is_eqcr,
            }
        raise
    return {"can_edit": True, "reason": None, "is_eqcr": is_eqcr}
