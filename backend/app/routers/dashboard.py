"""管理看板 API 路由

Phase 9 Task 1.10
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """关键指标聚合"""
    svc = DashboardService(db)
    return await svc.get_overview()


@router.get("/project-progress")
async def project_progress(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """项目进度列表"""
    svc = DashboardService(db)
    return await svc.get_project_progress()


@router.get("/staff-workload")
async def staff_workload(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """人员负荷排行"""
    svc = DashboardService(db)
    return await svc.get_staff_workload()


@router.get("/schedule")
async def schedule(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """人员排期甘特图数据"""
    svc = DashboardService(db)
    return await svc.get_schedule()


@router.get("/hours-heatmap")
async def hours_heatmap(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """工时热力图数据"""
    svc = DashboardService(db)
    return await svc.get_hours_heatmap()


@router.get("/risk-alerts")
async def risk_alerts(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """风险预警"""
    svc = DashboardService(db)
    return await svc.get_risk_alerts()


@router.get("/quality-metrics")
async def quality_metrics(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """审计质量指标"""
    svc = DashboardService(db)
    return await svc.get_quality_metrics()


@router.get("/group-progress")
async def group_progress(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """集团审计子公司进度对比"""
    svc = DashboardService(db)
    return await svc.get_group_progress()
