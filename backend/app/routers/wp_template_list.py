"""底稿模板列表 API（含适用性预判）

GET /api/workpapers/template-list — 按项目业务分类返回全部模板 + applicable 状态
GET /api/workpapers/business-category-reference — 返回业务分类参考数据

Requirements: 3.1, 3.3
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import Project, User
from app.services.business_category_service import (
    get_reference_data,
    get_template_list_with_applicability,
)
from app.services.procedure_scope_retention import TrimScopeUnavailable, load_trimmed_scope

router = APIRouter(prefix="/api/workpapers/template-list")


@router.get("")
async def get_template_list(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> list[dict[str, Any]]:
    """返回全部模板列表，按项目业务分类标注 applicable 状态。

    ``trimmed`` / ``trimmed_by``：该编码已在程序裁剪中标为不执行（``trimmed_by`` 是决定它的程序行编码，
    如 ``H3-2`` 跟随 ``H3``）；生成前的确认弹窗不预选、不可勾选。读不到裁剪结果返回 503。
    """
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()

    category = "C"
    if project and hasattr(project, "business_category"):
        category = project.business_category or "C"

    try:
        scope = await load_trimmed_scope(db, project_id)
    except TrimScopeUnavailable as e:
        raise HTTPException(status_code=503, detail=e.http_detail())
    items = []
    for item in get_template_list_with_applicability(category):
        owner = scope.trim_owner(item.get("wp_code"))
        items.append({**item, "trimmed": owner is not None, "trimmed_by": owner})
    return items


@router.get("/reference")
async def get_category_reference(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回业务分类参考数据（A/B/C 定义+质控措施）"""
    return get_reference_data()
