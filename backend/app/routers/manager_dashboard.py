"""项目经理看板 API 路由

Round 2 需求 1：GET /api/dashboard/manager/overview
Round 2 需求 8：GET /api/dashboard/manager/assignment-status
权限守卫：role='manager' 或 project_assignment.role IN ('manager','signing_partner')

路由前缀规范：与 dashboard.py 相同，内部带 /api/dashboard/manager，注册时不加额外前缀。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.manager_dashboard_service import ManagerDashboardService

router = APIRouter(prefix="/api/dashboard/manager", tags=["manager-dashboard"])


@router.get("/overview")
async def get_manager_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """项目经理看板总览 — 项目卡片 + 跨项目待办 + 团队负载

    权限: role='manager' 或 role='admin'，
    或通过 project_assignment.role IN ('manager','signing_partner') 有项目关联。
    数据范围由 ManagerDashboardService 内部权限守卫过滤。

    Redis 缓存 5 分钟。
    """
    svc = ManagerDashboardService(db)

    # Batch 1 P1.1: 权限守卫 + 数据范围共用一次项目查询
    project_ids = await svc._get_manager_project_ids(current_user)
    allowed_roles = ("admin", "manager", "partner")
    if current_user.role.value not in allowed_roles and not project_ids:
        raise HTTPException(status_code=403, detail="权限不足：需要项目经理或签字合伙人角色")

    return await svc.get_overview(current_user, project_ids=project_ids)


@router.get("/assignment-status")
async def get_assignment_status(
    days: int = Query(7, ge=1, le=90, description="查询最近 N 天的委派记录"),
    project_id: str | None = Query(None, description="可选项目 ID 筛选"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """委派已读回执 — 返回近 N 天委派记录及通知已读状态

    返回:
        [{wp_code, assignee_name, assigned_at, notification_read_at|null, is_overdue_unread}]

    48 小时未读标记 is_overdue_unread=true（查询时实时算，无 worker）。
    """
    import uuid as _uuid

    svc = ManagerDashboardService(db)

    # Batch 1 P1.1: 权限守卫 + 数据范围共用一次项目查询
    project_ids = await svc._get_manager_project_ids(current_user)
    allowed_roles = ("admin", "manager", "partner")
    if current_user.role.value not in allowed_roles and not project_ids:
        raise HTTPException(status_code=403, detail="权限不足：需要项目经理或签字合伙人角色")

    parsed_project_id: _uuid.UUID | None = None
    if project_id:
        try:
            parsed_project_id = _uuid.UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 project_id 格式")

    return await svc.get_assignment_status(
        current_user, days=days, project_id=parsed_project_id,
        project_ids=project_ids,
    )
