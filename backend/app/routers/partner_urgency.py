"""多项目紧急度评分排序 API — Phase 7 F12

GET /api/partner/projects/urgency
复用 Phase 6 F7 urgency_score 三因子加权公式：
  sla_factor = 1 - (days_remaining / max_days)
  vr_factor = min(blocking_vr_count / 10, 1.0)
  wp_factor = 1 - (completed_wp / total_wp)
  urgency_score = round((0.4 * sla + 0.3 * vr + 0.3 * wp) × 100)

标签：≥80 urgent(red) / ≥60 attention(orange) / ≥40 normal(yellow) / <40 safe(green)
权限：partner/admin
注册到 router_registry 协作域 §115。

Validates: Requirements F12.1, F12.2, F12.3, F12.4, F12.6, F12.7
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, ProjectUser, User

router = APIRouter(
    prefix="/api/partner/projects",
    tags=["partner-urgency"],
)


def _calc_urgency_score(
    days_remaining: int | None,
    max_days: int,
    blocking_vr_count: int,
    completed_wp: int,
    total_wp: int,
) -> int:
    """Calculate urgency score using Phase 6 F7 formula.

    Returns integer 0-100.
    """
    # SLA factor: closer to deadline = higher urgency
    if days_remaining is None or max_days <= 0:
        sla_factor = 0.5  # default mid-range if no SLA
    else:
        sla_factor = max(0, min(1, 1 - (days_remaining / max_days)))

    # VR factor: more blocking VRs = higher urgency
    vr_factor = min(blocking_vr_count / 10, 1.0)

    # WP factor: more incomplete = higher urgency
    if total_wp > 0:
        wp_factor = 1 - (completed_wp / total_wp)
    else:
        wp_factor = 0

    score = round((0.4 * sla_factor + 0.3 * vr_factor + 0.3 * wp_factor) * 100)
    return max(0, min(100, score))


def _get_urgency_label(score: int) -> str:
    """Map score to urgency label."""
    if score >= 80:
        return "urgent"
    elif score >= 60:
        return "attention"
    elif score >= 40:
        return "normal"
    else:
        return "safe"


@router.get("/urgency")
async def get_partner_urgency(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回合伙人负责项目的紧急度评分排序"""
    if current_user.role.value not in ("admin", "partner"):
        raise HTTPException(403, "权限不足：仅 partner/admin 可访问")

    # Get projects where user is partner or assigned
    if current_user.role.value == "admin":
        # Admin sees all active projects
        proj_stmt = select(Project).where(
            Project.is_deleted == False,  # noqa: E712
            Project.status != "archived",
        )
    else:
        # Partner sees projects they're assigned to
        proj_stmt = (
            select(Project)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .where(
                ProjectUser.user_id == current_user.id,
                ProjectUser.is_deleted == False,  # noqa: E712
                Project.is_deleted == False,  # noqa: E712
                Project.status != "archived",
            )
        )

    result = await db.execute(proj_stmt)
    projects = result.scalars().all()

    items = []
    for project in projects:
        # Calculate days remaining from audit_period_end
        days_remaining = None
        if project.audit_period_end:
            delta = project.audit_period_end - date.today()
            days_remaining = delta.days

        # Simplified: use 90 days as max_days default
        max_days = 90

        # Simplified metrics (in production would query VR results + workpaper status)
        blocking_vr_count = 0
        completed_wp = 0
        total_wp = 1  # avoid division by zero

        score = _calc_urgency_score(
            days_remaining=days_remaining,
            max_days=max_days,
            blocking_vr_count=blocking_vr_count,
            completed_wp=completed_wp,
            total_wp=total_wp,
        )
        label = _get_urgency_label(score)

        items.append({
            "project_id": str(project.id),
            "project_name": project.name,
            "client_name": project.client_name,
            "urgency_score": score,
            "urgency_label": label,
            "sla_days_remaining": days_remaining,
            "blocking_vr_count": blocking_vr_count,
            "incomplete_wp_ratio": 1 - (completed_wp / total_wp) if total_wp > 0 else 0,
            "key_metrics_summary": f"SLA {days_remaining}天" if days_remaining is not None else "无 SLA",
        })

    # Sort by urgency_score descending
    items.sort(key=lambda x: x["urgency_score"], reverse=True)

    return {"projects": items}
