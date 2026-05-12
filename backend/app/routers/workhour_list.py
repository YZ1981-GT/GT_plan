"""工时审批列表路由 — 补全前端 WorkHoursApproval.vue 所需端点

GET  /api/workhours          — 审批人视角的工时列表（支持 status/date_from/date_to 筛选）
GET  /api/workhours/summary  — 本周统计（已审批小时 + 待审批小时），减少 N+1 请求
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

router = APIRouter(prefix="/api", tags=["workhours"])


@router.get("/workhours")
async def list_workhours_for_approval(
    status: str | None = Query(None, description="筛选状态: draft/confirmed/approved"),
    date_from: date | None = Query(None, description="起始日期"),
    date_to: date | None = Query(None, description="截止日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["manager", "admin"])),
):
    """审批人视角的工时列表。

    - admin 看所有 confirmed/approved 工时
    - manager 只看自己管理项目的工时
    """
    q = (
        sa.select(
            WorkHour,
            Project.name.label("project_name"),
            StaffMember.name.label("staff_name"),
        )
        .join(Project, WorkHour.project_id == Project.id)
        .join(StaffMember, WorkHour.staff_id == StaffMember.id)
        .where(WorkHour.is_deleted == sa.false())
    )

    # 权限过滤：manager 只看自己管理的项目
    if current_user.role.value != "admin":
        managed_project_ids = (
            sa.select(ProjectAssignment.project_id)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                StaffMember.user_id == current_user.id,
                ProjectAssignment.is_deleted == sa.false(),
                ProjectAssignment.role.in_(["manager", "signing_partner"]),
            )
        )
        q = q.where(WorkHour.project_id.in_(managed_project_ids))

    if status:
        q = q.where(WorkHour.status == status)
    if date_from:
        q = q.where(WorkHour.work_date >= date_from)
    if date_to:
        q = q.where(WorkHour.work_date <= date_to)

    q = q.order_by(WorkHour.work_date.desc(), WorkHour.created_at.desc())

    rows = (await db.execute(q)).all()
    return {
        "items": [
            {
                "id": str(wh.id),
                "staff_id": str(wh.staff_id),
                "staff_name": staff_name,
                "project_id": str(wh.project_id),
                "project_name": project_name,
                "work_date": str(wh.work_date),
                "hours": float(wh.hours),
                "start_time": str(wh.start_time) if wh.start_time else None,
                "end_time": str(wh.end_time) if wh.end_time else None,
                "description": wh.description,
                "status": wh.status,
                "purpose": wh.purpose,
            }
            for wh, project_name, staff_name in rows
        ],
        "total": len(rows),
    }


@router.get("/workhours/summary")
async def workhours_weekly_summary(
    week: str | None = Query("current", description="current=本周"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["manager", "admin"])),
):
    """本周工时统计，一次返回已审批+待审批小时数，消除前端 N+1。"""
    today = date.today()
    # 计算本周一和本周日
    days_to_monday = today.weekday()  # Monday=0
    monday = today - timedelta(days=days_to_monday)
    sunday = monday + timedelta(days=6)

    # 权限过滤子查询
    project_filter = sa.true()
    if current_user.role.value != "admin":
        managed_project_ids = (
            sa.select(ProjectAssignment.project_id)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                StaffMember.user_id == current_user.id,
                ProjectAssignment.is_deleted == sa.false(),
                ProjectAssignment.role.in_(["manager", "signing_partner"]),
            )
        )
        project_filter = WorkHour.project_id.in_(managed_project_ids)

    base = sa.select(
        WorkHour.status,
        sa.func.coalesce(sa.func.sum(WorkHour.hours), 0).label("total_hours"),
    ).where(
        WorkHour.is_deleted == sa.false(),
        WorkHour.work_date >= monday,
        WorkHour.work_date <= sunday,
        project_filter,
        WorkHour.status.in_(["confirmed", "approved"]),
    ).group_by(WorkHour.status)

    rows = (await db.execute(base)).all()
    result = {"approved_hours": 0.0, "pending_hours": 0.0}
    for row in rows:
        if row.status == "approved":
            result["approved_hours"] = float(row.total_hours)
        elif row.status == "confirmed":
            result["pending_hours"] = float(row.total_hours)

    return result
