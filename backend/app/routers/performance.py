"""性能监控 API — Phase 8 Task 8.4"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.core import User
from app.services.performance_monitor import performance_monitor

router = APIRouter(prefix="/api/admin", tags=["performance"])


@router.get("/performance-stats")
async def get_performance_stats(
    current_user: User = Depends(get_current_user),
):
    """获取性能统计摘要。"""
    return performance_monitor.get_performance_stats()


@router.get("/performance-metrics")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
):
    """获取详细性能指标。"""
    return performance_monitor.get_metrics()


@router.get("/slow-queries")
async def get_slow_queries(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """获取慢查询列表。"""
    return {"queries": performance_monitor.get_slow_queries(limit)}
