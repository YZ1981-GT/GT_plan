"""issue_hints — 舞弊/违规计数 API 路由

GET /api/projects/{project_id}/issue-hints
返回舞弊/违规 issue hints 供 A17/A18 完成底稿 guidance 显示。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.issue_hints_service import get_issue_hints

router = APIRouter(prefix="/api/projects", tags=["issue-hints"])


@router.get("/{project_id}/issue-hints")
async def get_project_issue_hints(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目舞弊/违规问题提示（启发式，仅供提示）"""
    return await get_issue_hints(db, project_id)
