"""上年底稿对比 API — Round 4 需求 4

GET /api/projects/{project_id}/workpapers/{wp_id}/prior-year
  返回上年同 wp_code 的底稿文件 URL 和元数据；无对应底稿返回 404。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.continuous_audit_service import get_prior_year_workpaper

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}",
    tags=["底稿上年对比"],
)


@router.get("/prior-year")
async def get_prior_year(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """获取上年同底稿的元数据和文件 URL

    通过当前底稿的 wp_code 在上年项目中查找对应底稿。
    返回 {wp_id, wp_code, file_url, conclusion, audited_amount}。
    无对应上年底稿时返回 404。
    """
    result = await get_prior_year_workpaper(db, project_id, wp_id)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到对应的上年底稿")
    return result
