"""工时审批列表路由 — 统一查询 work_hour_entries（V117 迁移后唯一真源）

GET  /api/workhours          — 审批人视角的工时列表（支持 status/date_from/date_to 筛选）
GET  /api/workhours/summary  — 本周统计（已审批小时 + 待审批小时），减少 N+1 请求
"""

from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import Project, User
from app.models.staff_models import ProjectAssignment, StaffMember
from app.models.workhour_entry_models import WorkHourEntry

router = APIRouter(prefix="/api", tags=["workhours"])


@router.get("/workhours")
async def list_workhours_for_approval(
    status: str | None = Query(None, description="筛选状态: draft/submitted/approved/rejected"),
    date_from: date | None = Query(None, description="起始日期"),
    date_to: date | None = Query(None, description="截止日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["manager", "admin"])),
):
    """审批人视角的工时列表（查询 work_hour_entries 表）。

    - admin 看所有 submitted/approved/rejected 工时
    - manager 只看自己管理项目的工时
    """
    q = (
        sa.select(
            WorkHourEntry,
            Project.name.label("project_name"),
            User.username.label("staff_name"),
        )
        .join(Project, WorkHourEntry.project_id == Project.id)
        .join(User, WorkHourEntry.user_id == User.id)
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
        q = q.where(WorkHourEntry.project_id.in_(managed_project_ids))

    if status:
        q = q.where(WorkHourEntry.status == status)
    if date_from:
        q = q.where(WorkHourEntry.date >= date_from)
    if date_to:
        q = q.where(WorkHourEntry.date <= date_to)

    q = q.order_by(WorkHourEntry.date.desc(), WorkHourEntry.created_at.desc())

    rows = (await db.execute(q)).all()
    return {
        "items": [
            {
                "id": str(entry.id),
                "user_id": str(entry.user_id),
                "staff_name": staff_name,
                "project_id": str(entry.project_id),
                "project_name": project_name,
                "work_date": str(entry.date),
                "hours": float(entry.hours),
                "cycle": entry.cycle,
                "wp_code": entry.wp_code,
                "description": entry.description,
                "status": entry.status,
                "rejected_reason": entry.rejected_reason,
                "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
            }
            for entry, project_name, staff_name in rows
        ],
        "total": len(rows),
    }


@router.get("/workhours/summary")
async def workhours_weekly_summary(
    week: str | None = Query("current", description="current=本周"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["manager", "admin"])),
):
    """本周工时统计（查询 work_hour_entries），返回已审批+待审批小时数。"""
    today = date.today()
    days_to_monday = today.weekday()
    monday = today - timedelta(days=days_to_monday)
    sunday = monday + timedelta(days=6)

    # 权限过滤
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
        project_filter = WorkHourEntry.project_id.in_(managed_project_ids)

    base = sa.select(
        WorkHourEntry.status,
        sa.func.coalesce(sa.func.sum(WorkHourEntry.hours), 0).label("total_hours"),
    ).where(
        WorkHourEntry.date >= monday,
        WorkHourEntry.date <= sunday,
        project_filter,
        WorkHourEntry.status.in_(["submitted", "approved"]),
    ).group_by(WorkHourEntry.status)

    rows = (await db.execute(base)).all()
    result = {"approved_hours": 0.0, "pending_hours": 0.0, "pending_count": 0}
    for row in rows:
        if row.status == "approved":
            result["approved_hours"] = float(row.total_hours)
        elif row.status == "submitted":
            result["pending_hours"] = float(row.total_hours)

    # 待审批条数
    count_stmt = sa.select(sa.func.count()).where(
        WorkHourEntry.date >= monday,
        WorkHourEntry.date <= sunday,
        project_filter,
        WorkHourEntry.status == "submitted",
    )
    result["pending_count"] = (await db.execute(count_stmt)).scalar() or 0

    return result
