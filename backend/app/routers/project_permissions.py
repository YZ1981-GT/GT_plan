"""项目级权限 API 端点。

权限映射与写端点门禁共同使用 ``app.services.project_permissions``，
避免前端展示权限与后端实际授权出现漂移。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.project_permissions import (
    ALL_PERMISSIONS,
    PROJECT_ROLE_PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
    resolve_project_context,
)

router = APIRouter(prefix="/api/projects", tags=["project-permissions"])


@router.get("/{project_id}/my-permissions")
async def get_my_permissions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户在该项目的合并权限列表。"""
    context = await resolve_project_context(db, current_user, project_id)
    return {
        "permissions": sorted(context.permissions),
        "project_role": context.project_role,
        "system_role": context.system_role,
    }


@router.get("/{project_id}/my-role")
async def get_my_role(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回当前用户在该项目的角色和系统角色。"""
    context = await resolve_project_context(db, current_user, project_id)
    return {
        "project_role": context.project_role,
        "system_role": context.system_role,
    }
