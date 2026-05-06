"""底稿程序要求聚合 API — Round 4 需求 1

GET /api/projects/{project_id}/workpapers/{wp_id}/requirements
  聚合 wp_manuals + procedures + continuous_audit.prior_year_summary
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.workpaper_requirements_service import get_workpaper_requirements

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}",
    tags=["底稿程序要求"],
)


@router.get("/requirements")
async def get_requirements(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取底稿的程序要求聚合信息

    聚合三个数据源：
    - manual: 底稿操作手册内容（按循环）
    - procedures: 关联到本底稿的审计程序列表
    - prior_year_summary: 上年同底稿结论摘要
    """
    result = await get_workpaper_requirements(db, project_id, wp_id)
    return result
