"""待办聚合路由

Requirements: 1.1, 1.4

GET /api/projects/{project_id}/my-todo
返回当前用户在指定项目中的待办底稿列表，按紧急度降序排列。
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.my_todo_service import MyTodoResponse, get_my_todo

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/my-todo",
    tags=["my-todo"],
)


@router.get("", response_model=MyTodoResponse)
async def get_my_todo_list(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> MyTodoResponse:
    """获取当前用户的待办聚合列表。

    按紧急度降序排列：critical > high > medium > normal。
    性能目标：≤ 500ms（50 底稿规模）。
    """
    start_time = time.time()

    result = await get_my_todo(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "My todo requested: project_id=%s user_id=%s items=%d elapsed=%.1fms",
        project_id,
        current_user.id,
        result.total,
        elapsed_ms,
    )

    return result
