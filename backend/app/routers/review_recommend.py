"""复核分派智能推荐 API — Phase 7 F9

GET /api/projects/{id}/review-recommend?cycle={cycle}
三因子加权评分：历史复核记录 40% + 工时余量 30% + 循环专长 30%
返回 Top 3 候选人 + 评分明细。
权限：manager+
注册到 router_registry 协作域 §113。

Validates: Requirements F9.1, F9.2, F9.3, F9.4, F9.5, F9.6, F9.7, F9.8
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import ProjectUser, User
from app.models.workhour_entry_models import WorkHourEntry

router = APIRouter(
    prefix="/api/projects/{project_id}/review-recommend",
    tags=["review-recommend"],
)

# Constants
HISTORY_CAP = 10
STANDARD_WEEKLY_HOURS = 40


def _calc_recommendation_score(
    review_count_in_cycle: int,
    current_week_hours: float,
    matched_cycles: int,
    total_cycles: int,
) -> dict:
    """Calculate three-factor weighted score."""
    history_factor = min(review_count_in_cycle / HISTORY_CAP, 1.0)
    capacity_factor = max(0, (STANDARD_WEEKLY_HOURS - current_week_hours) / STANDARD_WEEKLY_HOURS)
    expertise_factor = (matched_cycles / total_cycles) if total_cycles > 0 else 0

    score = 0.4 * history_factor + 0.3 * capacity_factor + 0.3 * expertise_factor
    return {
        "score": round(score, 4),
        "history_score": round(history_factor, 4),
        "capacity_score": round(capacity_factor, 4),
        "expertise_score": round(expertise_factor, 4),
    }


@router.get("")
async def recommend_reviewer(
    project_id: UUID,
    cycle: str = Query(..., description="目标循环"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """推荐复核人（Top 3）"""
    # Permission: manager/partner/admin
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(403, "权限不足：仅 manager+ 可访问")

    # Get project team members
    team_stmt = select(ProjectUser).where(
        ProjectUser.project_id == project_id,
        ProjectUser.is_deleted == False,  # noqa: E712
    )
    team_result = await db.execute(team_stmt)
    team_members = team_result.scalars().all()

    if not team_members:
        return {"candidates": [], "total_team_size": 0}

    candidates = []
    for member in team_members:
        user_id = member.user_id

        # Skip the current user (requester shouldn't review their own work)
        if user_id == current_user.id:
            continue

        # Factor 1: History — count work_hour_entries in this cycle for this project
        history_stmt = select(func.count()).where(
            WorkHourEntry.user_id == user_id,
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.cycle == cycle,
        )
        history_result = await db.execute(history_stmt)
        review_count = history_result.scalar() or 0

        # Factor 2: Capacity — current week hours across all projects
        from datetime import date, timedelta

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        capacity_stmt = select(
            func.coalesce(func.sum(WorkHourEntry.hours), 0)
        ).where(
            WorkHourEntry.user_id == user_id,
            WorkHourEntry.date >= week_start,
            WorkHourEntry.date <= week_end,
        )
        capacity_result = await db.execute(capacity_stmt)
        current_week_hours = float(capacity_result.scalar() or 0)

        # Factor 3: Expertise — distinct cycles this user has worked on in this project
        expertise_stmt = select(
            func.count(func.distinct(WorkHourEntry.cycle))
        ).where(
            WorkHourEntry.user_id == user_id,
            WorkHourEntry.project_id == project_id,
        )
        expertise_result = await db.execute(expertise_stmt)
        total_cycles_worked = expertise_result.scalar() or 0

        # Check if user has worked on the target cycle
        matched_stmt = select(func.count()).where(
            WorkHourEntry.user_id == user_id,
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.cycle == cycle,
        )
        matched_result = await db.execute(matched_stmt)
        matched_cycles = 1 if (matched_result.scalar() or 0) > 0 else 0

        scores = _calc_recommendation_score(
            review_count_in_cycle=review_count,
            current_week_hours=current_week_hours,
            matched_cycles=matched_cycles,
            total_cycles=max(total_cycles_worked, 1),
        )

        # Get user name
        user_stmt = select(User).where(User.id == user_id)
        user_result = await db.execute(user_stmt)
        user_obj = user_result.scalar_one_or_none()
        user_name = user_obj.username if user_obj else str(user_id)

        candidates.append({
            "user_id": str(user_id),
            "user_name": user_name,
            "current_week_hours": current_week_hours,
            "review_count_in_cycle": review_count,
            **scores,
        })

    # Sort by score descending, return Top 3 (or all if < 3)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    top_candidates = candidates[:3] if len(candidates) >= 3 else candidates

    return {
        "candidates": top_candidates,
        "total_team_size": len(team_members),
    }
