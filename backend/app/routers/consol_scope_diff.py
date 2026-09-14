"""合并范围校对路由 — 树形(projects 三代码) vs consol_scope 差异

group-tree-architecture 需求 9：

- GET  /api/consolidation/{project_id}/scope-diff  返回 in_tree_not_scope / in_scope_not_tree 集合差
- POST /api/consolidation/{project_id}/sync-scope   仅增量添加树形子企业到 consol_scope（不自动删除）

差异提示不阻塞树形展示（Req 9.5）；sync-scope 只增不删（Req 9.4）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.scope_diff_service import compute_scope_diff, sync_scope

router = APIRouter(prefix="/api/consolidation", tags=["合并范围校对"])


class ScopeDiffResponse(BaseModel):
    in_tree_not_scope: list[dict]   # 树形有、合并范围无（待纳入）
    in_scope_not_tree: list[dict]   # 合并范围有、树形无（待移除）


class SyncScopeRequest(BaseModel):
    company_codes: list[str]        # 要新增到合并范围的子企业代码列表


class SyncScopeResponse(BaseModel):
    added: int                      # 实际新增数（已存在的跳过）


@router.get("/{project_id}/scope-diff", response_model=ScopeDiffResponse)
async def get_scope_diff(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """返回树形 vs 合并范围差异（Property 10：精确集合差）。"""
    diff = await compute_scope_diff(db, project_id)
    return ScopeDiffResponse(**diff)


@router.post("/{project_id}/sync-scope", response_model=SyncScopeResponse)
async def post_sync_scope(
    project_id: UUID,
    data: SyncScopeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """仅增量添加树形子企业到 consol_scope（不自动删除多出条目，Req 9.4）。"""
    added = await sync_scope(db, project_id, data.company_codes)

    # 审计留痕（与现有 consol_scope 写操作一致：action=consol.scope.change）
    if added:
        from app.services.consol_audit_helper import log_consol_action
        await log_consol_action(
            db,
            user_id=user.id,
            project_id=project_id,
            action="consol.scope.change",
            resource_type="consol_scope",
            resource_id=str(project_id),
            before=None,
            after={"action": "sync_scope_add", "added": added, "company_codes": data.company_codes},
        )
    await db.commit()
    return SyncScopeResponse(added=added)
