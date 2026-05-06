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


# ── Phase 8+: 管理看板增强查询 ──────────────────────────────


@router.get("/project-staff-hours")
async def project_staff_hours(
    project_id: str = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """按项目维度查询人员及工时情况"""
    from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
    from app.models.core import Project
    import sqlalchemy as sa
    from datetime import date, timedelta

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    q = (
        sa.select(
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Project.client_name,
            StaffMember.id.label("staff_id"),
            StaffMember.name.label("staff_name"),
            StaffMember.title,
            ProjectAssignment.role,
            sa.func.coalesce(
                sa.select(sa.func.sum(WorkHour.hours))
                .where(
                    WorkHour.staff_id == StaffMember.id,
                    WorkHour.project_id == Project.id,
                    WorkHour.is_deleted == False,
                )
                .correlate(StaffMember, Project)
                .scalar_subquery(),
                0,
            ).label("total_hours"),
            sa.func.coalesce(
                sa.select(sa.func.sum(WorkHour.hours))
                .where(
                    WorkHour.staff_id == StaffMember.id,
                    WorkHour.project_id == Project.id,
                    WorkHour.work_date >= week_start,
                    WorkHour.is_deleted == False,
                )
                .correlate(StaffMember, Project)
                .scalar_subquery(),
                0,
            ).label("week_hours"),
        )
        .join(ProjectAssignment, ProjectAssignment.project_id == Project.id)
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            Project.is_deleted == False,
            ProjectAssignment.is_deleted == False,
            StaffMember.is_deleted == False,
        )
    )

    if project_id:
        q = q.where(Project.id == project_id)

    q = q.order_by(Project.name, StaffMember.name)
    rows = (await db.execute(q)).all()

    return [
        {
            "project_id": str(r.project_id),
            "project_name": r.project_name,
            "client_name": r.client_name,
            "staff_id": str(r.staff_id),
            "staff_name": r.staff_name,
            "title": r.title,
            "role": r.role,
            "total_hours": float(r.total_hours),
            "week_hours": float(r.week_hours),
        }
        for r in rows
    ]


@router.get("/staff-detail")
async def staff_detail(
    staff_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """按人员查询负责的项目、工时和未来一周安排"""
    from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour
    from app.models.core import Project
    import sqlalchemy as sa
    from datetime import date, timedelta
    from uuid import UUID

    sid = UUID(staff_id)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    next_week_end = today + timedelta(days=7)

    # 基本信息
    staff_q = sa.select(StaffMember).where(StaffMember.id == sid, StaffMember.is_deleted == False)
    staff = (await db.execute(staff_q)).scalar_one_or_none()
    if not staff:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="人员不存在")

    # 参与的项目
    proj_q = (
        sa.select(
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Project.client_name,
            Project.status,
            ProjectAssignment.role,
            ProjectAssignment.assigned_cycles,
        )
        .join(ProjectAssignment, ProjectAssignment.project_id == Project.id)
        .where(
            ProjectAssignment.staff_id == sid,
            ProjectAssignment.is_deleted == False,
            Project.is_deleted == False,
        )
        .order_by(Project.name)
    )
    projects = (await db.execute(proj_q)).all()

    # 本周工时
    wh_q = (
        sa.select(
            WorkHour.work_date,
            WorkHour.hours,
            WorkHour.description,
            Project.name.label("project_name"),
        )
        .join(Project, WorkHour.project_id == Project.id)
        .where(
            WorkHour.staff_id == sid,
            WorkHour.work_date >= week_start,
            WorkHour.is_deleted == False,
        )
        .order_by(WorkHour.work_date)
    )
    work_hours = (await db.execute(wh_q)).all()

    # 未来一周安排（基于参与的活跃项目）
    active_projects = [p for p in projects if p.status in ("planning", "execution", "completion")]

    return {
        "staff": {
            "id": str(staff.id),
            "name": staff.name,
            "title": staff.title,
            "department": staff.department,
            "phone": staff.phone,
        },
        "projects": [
            {
                "project_id": str(p.project_id),
                "project_name": p.project_name,
                "client_name": p.client_name,
                "status": p.status,
                "role": p.role,
                "assigned_cycles": p.assigned_cycles,
            }
            for p in projects
        ],
        "week_hours": [
            {
                "date": str(wh.work_date),
                "hours": float(wh.hours),
                "description": wh.description,
                "project_name": wh.project_name,
            }
            for wh in work_hours
        ],
        "week_total": sum(float(wh.hours) for wh in work_hours),
        "next_week_projects": [
            {
                "project_name": p.project_name,
                "client_name": p.client_name,
                "role": p.role,
            }
            for p in active_projects
        ],
    }


@router.get("/available-staff")
async def available_staff(
    days: int = 7,
    max_hours: float = 30,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """查询未来一周可用人员（本周工时低于阈值的人员）"""
    from app.models.staff_models import StaffMember, WorkHour, ProjectAssignment
    import sqlalchemy as sa
    from datetime import date, timedelta

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    q = (
        sa.select(
            StaffMember.id,
            StaffMember.name,
            StaffMember.title,
            StaffMember.department,
            sa.func.count(sa.distinct(ProjectAssignment.project_id)).label("project_count"),
            sa.func.coalesce(
                sa.select(sa.func.sum(WorkHour.hours))
                .where(
                    WorkHour.staff_id == StaffMember.id,
                    WorkHour.work_date >= week_start,
                    WorkHour.work_date <= today,
                    WorkHour.is_deleted == False,
                )
                .correlate(StaffMember)
                .scalar_subquery(),
                0,
            ).label("week_hours"),
        )
        .outerjoin(ProjectAssignment, sa.and_(
            ProjectAssignment.staff_id == StaffMember.id,
            ProjectAssignment.is_deleted == False,
        ))
        .where(StaffMember.is_deleted == False)
        .group_by(StaffMember.id, StaffMember.name, StaffMember.title, StaffMember.department)
        .having(
            sa.func.coalesce(
                sa.select(sa.func.sum(WorkHour.hours))
                .where(
                    WorkHour.staff_id == StaffMember.id,
                    WorkHour.work_date >= week_start,
                    WorkHour.work_date <= today,
                    WorkHour.is_deleted == False,
                )
                .correlate(StaffMember)
                .scalar_subquery(),
                0,
            ) < max_hours
        )
        .order_by(sa.asc("week_hours"))
        .limit(50)
    )
    rows = (await db.execute(q)).all()

    return [
        {
            "staff_id": str(r.id),
            "name": r.name,
            "title": r.title,
            "department": r.department,
            "project_count": r.project_count,
            "week_hours": float(r.week_hours),
            "available_hours": round(max_hours - float(r.week_hours), 1),
        }
        for r in rows
    ]


@router.get("/stats/trend")
async def stats_trend(
    project_id: str | None = None,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = DashboardService(db)
    return await svc.get_stats_trend(project_id=project_id, days=days)
