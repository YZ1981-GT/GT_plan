"""EQCR 工作台列表 + 项目总览"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_service import EqcrService

router = APIRouter()


@router.get("/projects")
async def list_my_eqcr_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回本人作为 EQCR 的项目卡片列表（签字日升序）。"""
    svc = EqcrService(db)
    return await svc.list_my_projects(current_user.id)


@router.get("/projects/{project_id}/overview")
async def get_eqcr_project_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目 EQCR 总览数据（用于 EqcrProjectView 详情页壳）。"""
    svc = EqcrService(db)
    data = await svc.get_project_overview(current_user.id, project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return data
