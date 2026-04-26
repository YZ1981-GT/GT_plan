"""角色上下文 API — 多角色×多项目×多重身份"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.role_context_service import RoleContextService

router = APIRouter(prefix="/api/role-context", tags=["role-context"])


@router.get("/me")
async def get_my_context(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的全局角色上下文（系统角色+所有项目角色+最高角色）"""
    svc = RoleContextService(db)
    return await svc.get_global_context(current_user.id)


@router.get("/me/nav")
async def get_my_nav(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户可见的导航菜单"""
    svc = RoleContextService(db)
    return await svc.get_nav_items(current_user.id)


@router.get("/me/homepage")
async def get_my_homepage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取首页个性化内容"""
    svc = RoleContextService(db)
    return await svc.get_homepage_content(current_user.id)


@router.get("/project/{project_id}")
async def get_project_role(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户在特定项目中的角色"""
    svc = RoleContextService(db)
    return await svc.get_project_role(current_user.id, project_id)
