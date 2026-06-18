"""workpaper_summaries — 底稿摘要 API 路由

GET /api/projects/{project_id}/workpaper-summaries/{key}

返回指定 key 的底稿摘要数据（供 A17/A18 等完成阶段底稿消费）。
设计决策：ready=False 时仍返回 HTTP 200（非 409），前端 toast 提示。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.workpaper_summaries_service import get_workpaper_summary

router = APIRouter(prefix="/api/projects", tags=["workpaper-summaries"])


@router.get("/{project_id}/workpaper-summaries/{key}")
async def get_project_workpaper_summary(
    project_id: UUID,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取底稿摘要（ready=false 时 HTTP 200 + reason）"""
    result = await get_workpaper_summary(db, project_id, key)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"未知摘要 key: {key}",
        )
    return result
