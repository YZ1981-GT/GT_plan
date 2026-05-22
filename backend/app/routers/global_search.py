"""全局搜索路由 — Phase 1 F1

GET /api/search/global?q={keyword}&project_id={optional}

支持搜索：底稿编号/科目名称/报表行/项目名称
模糊匹配 + 拼音首字母匹配
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.global_search_service import global_search

router = APIRouter(prefix="/api/search", tags=["全局搜索"])


@router.get("/global")
async def search_global(
    q: str = Query(..., min_length=2, max_length=50, description="搜索关键词"),
    project_id: UUID | None = Query(None, description="限定项目范围（可选）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全局搜索 — 聚合底稿/科目/报表行/项目四类实体

    - q: 搜索关键词（2~50 字符）
    - project_id: 可选，传入时仅搜索该项目范围
    - 返回最多 50 条结果，按相关度降序排列
    """
    try:
        results = await global_search(
            db=db,
            q=q,
            user_id=current_user.id,
            project_id=project_id,
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索服务异常: {str(e)}")
