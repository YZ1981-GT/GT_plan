"""工时预算 vs 实际对比 API — Phase 7 F8

GET /api/projects/{id}/workhours/budget-vs-actual
按循环 + 按人员聚合，超预算 120% 标记。
权限：manager+
注册到 router_registry 协作域 §112。

Validates: Requirements F8.1, F8.2, F8.3, F8.4, F8.7
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workhour_entry_models import WorkHourEntry

router = APIRouter(
    prefix="/api/projects/{project_id}/workhours/budget-vs-actual",
    tags=["workhours-budget"],
)


@router.get("")
async def get_budget_compare(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回预算 vs 实际对比数据"""
    # Permission: manager/partner/admin
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(403, "权限不足：仅 manager+ 可访问")

    # Load project budget_config
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    budget_config = project.budget_config
    if not budget_config:
        return {
            "by_cycle": [],
            "by_user": [],
            "warning": "项目未配置工时预算（budget_config 为空）",
        }

    # Aggregate actual hours by cycle
    cycle_stmt = (
        select(
            WorkHourEntry.cycle,
            func.coalesce(func.sum(WorkHourEntry.hours), 0).label("actual"),
        )
        .where(WorkHourEntry.project_id == project_id)
        .group_by(WorkHourEntry.cycle)
    )
    cycle_result = await db.execute(cycle_stmt)
    cycle_actuals = {row.cycle: float(row.actual) for row in cycle_result}

    # Build by_cycle response
    by_cycle_budget = budget_config.get("by_cycle", {})
    by_cycle = []
    for cycle_name, budget_hours in by_cycle_budget.items():
        actual = cycle_actuals.get(cycle_name, 0)
        budget_h = float(budget_hours)
        variance_pct = ((actual - budget_h) / budget_h * 100) if budget_h > 0 else 0
        by_cycle.append({
            "cycle_name": cycle_name,
            "budget_hours": budget_h,
            "actual_hours": actual,
            "variance_pct": round(variance_pct, 1),
            "is_over_budget": variance_pct > 20,
        })

    # Aggregate actual hours by user
    user_stmt = (
        select(
            WorkHourEntry.user_id,
            func.coalesce(func.sum(WorkHourEntry.hours), 0).label("actual"),
        )
        .where(WorkHourEntry.project_id == project_id)
        .group_by(WorkHourEntry.user_id)
    )
    user_result = await db.execute(user_stmt)
    user_actuals = {str(row.user_id): float(row.actual) for row in user_result}

    # Build by_user response
    by_user_budget = budget_config.get("by_user", {})
    by_user = []
    for user_id_str, budget_hours in by_user_budget.items():
        actual = user_actuals.get(user_id_str, 0)
        budget_h = float(budget_hours)
        variance_pct = ((actual - budget_h) / budget_h * 100) if budget_h > 0 else 0
        by_user.append({
            "user_id": user_id_str,
            "budget_hours": budget_h,
            "actual_hours": actual,
            "variance_pct": round(variance_pct, 1),
            "is_over_budget": variance_pct > 20,
        })

    return {"by_cycle": by_cycle, "by_user": by_user}
