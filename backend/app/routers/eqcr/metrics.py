"""EQCR 指标仪表盘端点"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.staff_models import ProjectAssignment, StaffMember

router = APIRouter()


@router.get("/metrics")
async def get_eqcr_metrics(
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 年度指标仪表盘（需求 10）。仅 admin / partner 可见。"""
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in ("admin", "partner"):
        raise HTTPException(
            status_code=403,
            detail="仅 admin 或 partner 可访问 EQCR 指标仪表盘",
        )

    from app.models.eqcr_models import EqcrOpinion, EqcrDisagreementResolution
    from app.models.staff_models import WorkHour

    target_year = year or datetime.now(timezone.utc).year

    eqcr_assignments_q = (
        select(
            ProjectAssignment.staff_id,
            StaffMember.name.label("staff_name"),
            func.count(ProjectAssignment.id).label("project_count"),
        )
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.role == "eqcr",
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
        .group_by(ProjectAssignment.staff_id, StaffMember.name)
    )
    eqcr_rows = (await db.execute(eqcr_assignments_q)).all()

    metrics = []
    for row in eqcr_rows:
        staff_id = row.staff_id
        staff_name = row.staff_name
        project_count = row.project_count

        hours_q = select(
            func.coalesce(func.sum(WorkHour.hours), 0)
        ).where(
            WorkHour.staff_id == staff_id,
            WorkHour.purpose == "eqcr",
            WorkHour.status != "tracking",
            WorkHour.is_deleted == False,  # noqa: E712
            extract("year", WorkHour.work_date) == target_year,
        )
        total_hours = float((await db.execute(hours_q)).scalar_one())

        proj_ids_q = select(ProjectAssignment.project_id).where(
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.role == "eqcr",
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
        proj_ids = list((await db.execute(proj_ids_q)).scalars().all())

        disagreement_count = 0
        total_opinions = 0
        if proj_ids:
            disagree_q = select(func.count()).where(
                EqcrOpinion.project_id.in_(proj_ids),
                EqcrOpinion.verdict == "disagree",
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            disagreement_count = (await db.execute(disagree_q)).scalar_one()

            total_q = select(func.count()).where(
                EqcrOpinion.project_id.in_(proj_ids),
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            total_opinions = (await db.execute(total_q)).scalar_one()

        disagreement_rate = (
            round(disagreement_count / total_opinions * 100, 1)
            if total_opinions > 0
            else 0.0
        )

        material_findings = 0
        if proj_ids:
            findings_q = select(func.count()).where(
                EqcrDisagreementResolution.project_id.in_(proj_ids),
                EqcrDisagreementResolution.resolved_at.is_(None),
            )
            material_findings = (await db.execute(findings_q)).scalar_one()

        metrics.append({
            "eqcr_id": str(staff_id),
            "eqcr_name": staff_name,
            "project_count": project_count,
            "total_hours": round(total_hours, 1),
            "disagreement_count": disagreement_count,
            "disagreement_rate": disagreement_rate,
            "material_findings_count": material_findings,
        })

    return {
        "year": target_year,
        "metrics": metrics,
    }
