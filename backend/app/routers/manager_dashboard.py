"""项目经理看板 API 路由

Round 2 需求 1：GET /api/dashboard/manager/overview
Round 2 需求 8：GET /api/dashboard/manager/assignment-status
Phase 6 F7：GET /api/dashboard/manager/projects-overview
权限守卫：role='manager' 或 project_assignment.role IN ('manager','signing_partner')

路由前缀规范：与 dashboard.py 相同，内部带 /api/dashboard/manager，注册时不加额外前缀。
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workpaper_models import (
    ReviewRecord,
    WpIndex,
    WpReviewStatus,
    WpStatus,
    WorkingPaper,
)
from app.services.manager_dashboard_service import ManagerDashboardService

logger = logging.getLogger(__name__)

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



# ---------------------------------------------------------------------------
# Phase 6 F7: projects-overview — 经理项目群总览
# ---------------------------------------------------------------------------

# urgency_score 常量
VR_CAP = 10  # blocking VR 上限 cap
MAX_SLA_DAYS = 90  # SLA 最大天数（归一化基准）


def _calc_urgency_score(
    days_remaining: float,
    blocking_vr_count: int,
    completed_wp: int,
    total_wp: int,
) -> float:
    """计算 urgency_score = 0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor

    sla_factor: 1 - (days_remaining / max_days)，剩余越少越高
    vr_factor: min(blocking_vr_count / VR_CAP, 1.0)
    wp_factor: 1 - (completed_wp / total_wp)，未完成比例
    """
    # SLA factor: clamp days_remaining to [0, MAX_SLA_DAYS]
    clamped_days = max(0.0, min(float(days_remaining), float(MAX_SLA_DAYS)))
    sla_factor = 1.0 - (clamped_days / MAX_SLA_DAYS)

    # VR factor
    vr_factor = min(blocking_vr_count / VR_CAP, 1.0)

    # WP factor
    if total_wp > 0:
        wp_factor = 1.0 - (completed_wp / total_wp)
    else:
        wp_factor = 0.0

    return round(0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor, 4)


@router.get("/projects-overview")
async def get_projects_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """经理项目群总览 — 按 urgency_score 降序排列

    Requirements: F7.1, F7.2, F7.3, F7.4
    权限: 仅 manager/admin 可访问
    """
    # RBAC check
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail={"message": "权限不足", "message_en": "Insufficient permissions"})

    # Query projects where manager_id = current_user.id (admin sees all managed projects)
    stmt = select(Project).where(
        Project.is_deleted == False,  # noqa: E712
    )
    if user_role != "admin":
        stmt = stmt.where(Project.manager_id == current_user.id)

    result = await db.execute(stmt)
    projects = result.scalars().all()

    if not projects:
        return {"projects": []}

    project_list = []
    for proj in projects:
        project_id = proj.id

        # Get all wp_index entries for this project
        wp_idx_stmt = select(WpIndex).where(
            WpIndex.project_id == project_id,
            WpIndex.is_deleted == False,  # noqa: E712
        )
        wp_idx_result = await db.execute(wp_idx_stmt)
        wp_indices = wp_idx_result.scalars().all()

        total_wp = len(wp_indices)
        completed_wp = sum(1 for w in wp_indices if w.status == WpStatus.review_passed)

        # Overall progress
        overall_progress = round((completed_wp / total_wp * 100) if total_wp > 0 else 0, 1)

        # Cycle progress: group by audit_cycle
        cycle_map: dict[str, dict] = {}
        for wi in wp_indices:
            cycle = wi.audit_cycle or "other"
            if cycle not in cycle_map:
                cycle_map[cycle] = {"completed": 0, "total": 0}
            cycle_map[cycle]["total"] += 1
            if wi.status == WpStatus.review_passed:
                cycle_map[cycle]["completed"] += 1

        cycle_progress = []
        for cycle_name, counts in sorted(cycle_map.items()):
            pct = round((counts["completed"] / counts["total"] * 100) if counts["total"] > 0 else 0, 1)
            cycle_progress.append({
                "cycle": cycle_name,
                "completed": counts["completed"],
                "total": counts["total"],
                "pct": pct,
            })

        # Blocking VR count: review records with status='open' on this project's workpapers
        blocking_vr_stmt = (
            select(func.count(ReviewRecord.id))
            .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                ReviewRecord.status == "open",
                ReviewRecord.is_deleted == False,  # noqa: E712
                ReviewRecord.priority == "must_fix",
            )
        )
        blocking_vr_result = await db.execute(blocking_vr_stmt)
        blocking_vr_count = blocking_vr_result.scalar() or 0

        # Unresolved review count (all open reviews)
        unresolved_stmt = (
            select(func.count(ReviewRecord.id))
            .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                ReviewRecord.status == "open",
                ReviewRecord.is_deleted == False,  # noqa: E712
            )
        )
        unresolved_result = await db.execute(unresolved_stmt)
        unresolved_review_count = unresolved_result.scalar() or 0

        # SLA days remaining: audit_period_end - today
        today = date.today()
        if proj.audit_period_end:
            days_remaining = (proj.audit_period_end - today).days
        else:
            days_remaining = MAX_SLA_DAYS  # No deadline = no urgency from SLA

        # Calculate urgency score
        sla_urgency_score = _calc_urgency_score(
            days_remaining=days_remaining,
            blocking_vr_count=blocking_vr_count,
            completed_wp=completed_wp,
            total_wp=total_wp,
        )

        project_list.append({
            "project_id": str(project_id),
            "project_name": proj.name,
            "client_name": proj.client_name,
            "overall_progress": overall_progress,
            "cycle_progress": cycle_progress,
            "sla_urgency_score": sla_urgency_score,
            "blocking_vr_count": blocking_vr_count,
            "unresolved_review_count": unresolved_review_count,
        })

    # Sort by sla_urgency_score descending
    project_list.sort(key=lambda p: p["sla_urgency_score"], reverse=True)

    return {"projects": project_list}
