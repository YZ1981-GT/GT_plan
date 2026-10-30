"""角色作业台 API 端点

GET /api/projects/{project_id}/role-workbench?role=auditor|manager|partner

Requirements: 1.1, 2.1, 4.1
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/role-workbench", tags=["role-workbench"])


@router.get("")
async def get_role_workbench(
    project_id: UUID,
    role: str = Query(..., description="角色: auditor / manager / partner"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取角色作业台数据。

    按角色返回不同 section 组合，每个 item 包含 route 或 missing_reason。
    """
    from app.services.role_workbench_facade import RoleWorkbenchFacade

    user_id = UUID(str(current_user.id)) if hasattr(current_user, "id") else UUID("00000000-0000-0000-0000-000000000000")

    try:
        facade = RoleWorkbenchFacade(db=db, project_id=project_id, user_id=user_id)
        result = await facade.get_workbench(role)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[RoleWorkbench] unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="作业台数据加载失败")

