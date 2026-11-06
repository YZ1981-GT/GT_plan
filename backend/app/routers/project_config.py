"""项目级配置中心路由。

端点：
- ``GET  /api/projects/{project_id}/config``：项目只读权限；
- ``PUT  /api/projects/{project_id}/config``：``project:edit`` 权限。

配置字段的读取、更新和 ``flush`` 均由 :mod:`project_config_service` 处理；本模块是
唯一的提交/回滚边界。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access, require_project_permission
from app.models.core import User
from app.schemas.project_config import (
    ProjectConfigResponse,
    ProjectConfigUpdate,
    ProjectConfigUpdateResponse,
)
from app.services.project_config_service import ProjectConfigService

router = APIRouter(
    prefix="/api/projects/{project_id}/config",
    tags=["project-config"],
)


@router.get("", response_model=ProjectConfigResponse)
async def get_project_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> ProjectConfigResponse:
    """读取当前项目的完整配置。"""
    del current_user
    return await ProjectConfigService(db).get_config(project_id)


@router.put("", response_model=ProjectConfigUpdateResponse)
async def update_project_config(
    project_id: UUID,
    body: ProjectConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_permission("project:edit")),
) -> ProjectConfigUpdateResponse:
    """更新项目配置，并由路由统一提交或回滚。"""
    del current_user
    try:
        result = await ProjectConfigService(db).update_config(project_id, body)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise
