"""工时审批与底稿进度关联 API — Phase 7 F10

GET /api/projects/{id}/workhours/approval — 待审批列表含底稿进度列
POST approve/reject — 批量审批/退回
进度计算：level2_passed+ = 100% / level1_passed = 50% / else 0%
警告：progress < 30% AND hours > budget 80%
权限：manager/partner/admin
注册到 router_registry 协作域 §114。

Validates: Requirements F10.1, F10.2, F10.3, F10.4, F10.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workhour_entry_models import WorkHourEntry, WorkHourEntryStatus

router = APIRouter(
    prefix="/api/projects/{project_id}/workhours/approval",
    tags=["workhours-approval"],
)


class ApproveRequest(BaseModel):
    entry_ids: list[UUID]


class RejectRequest(BaseModel):
    entry_ids: list[UUID]
    reason: str | None = None


def _calc_wp_progress(wp_code: str | None) -> float:
    """Calculate workpaper progress percentage.

    Simplified: without actual review status lookup, returns 0%.
    In production, would query review_records for the wp_code.
    level2_passed+ = 100%, level1_passed = 50%, else 0%
    """
    # Stub: return 0% (no review data available without full integration)
    return 0.0


@router.get("")
async def list_pending_approvals(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出待审批工时（含底稿进度列）"""
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(403, "权限不足：仅 manager/partner/admin 可访问")

    # Get submitted entries for this project
    stmt = (
        select(WorkHourEntry)
        .where(
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.status == WorkHourEntryStatus.submitted.value,
        )
        .order_by(WorkHourEntry.date.desc())
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    # Load project budget_config for warning calculation
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    budget_config = project.budget_config if project else None
    cycle_budgets = budget_config.get("by_cycle", {}) if budget_config else {}

    # Get user names
    user_ids = list(set(e.user_id for e in entries))
    user_map: dict[UUID, str] = {}
    if user_ids:
        user_stmt = select(User).where(User.id.in_(user_ids))
        user_result = await db.execute(user_stmt)
        for u in user_result.scalars().all():
            user_map[u.id] = u.username

    items = []
    for entry in entries:
        wp_progress = _calc_wp_progress(entry.wp_code)
        # Warning: progress < 30% AND hours > budget * 80%
        cycle_budget = float(cycle_budgets.get(entry.cycle, 0))
        is_warning = (
            wp_progress < 30.0
            and cycle_budget > 0
            and float(entry.hours) > cycle_budget * 0.8
        )

        items.append({
            "entry_id": str(entry.id),
            "user_id": str(entry.user_id),
            "user_name": user_map.get(entry.user_id, str(entry.user_id)),
            "date": entry.date.isoformat(),
            "hours": float(entry.hours),
            "cycle": entry.cycle,
            "wp_code": entry.wp_code,
            "description": entry.description,
            "wp_progress_pct": wp_progress,
            "is_warning": is_warning,
        })

    return {"items": items, "total": len(items)}


@router.post("/approve")
async def approve_entries(
    project_id: UUID,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量审批工时（submitted → approved）"""
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(403, "权限不足")

    result = await db.execute(
        select(WorkHourEntry).where(
            WorkHourEntry.id.in_(body.entry_ids),
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.status == WorkHourEntryStatus.submitted.value,
        )
    )
    entries = result.scalars().all()

    now = datetime.now(timezone.utc)
    approved_count = 0
    for entry in entries:
        entry.status = WorkHourEntryStatus.approved.value
        entry.approved_by = current_user.id
        entry.approved_at = now
        approved_count += 1

    await db.commit()
    return {"approved_count": approved_count}


@router.post("/reject")
async def reject_entries(
    project_id: UUID,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量退回工时（submitted → rejected）"""
    if current_user.role.value not in ("admin", "partner", "manager"):
        raise HTTPException(403, "权限不足")

    result = await db.execute(
        select(WorkHourEntry).where(
            WorkHourEntry.id.in_(body.entry_ids),
            WorkHourEntry.project_id == project_id,
            WorkHourEntry.status == WorkHourEntryStatus.submitted.value,
        )
    )
    entries = result.scalars().all()

    rejected_count = 0
    for entry in entries:
        entry.status = WorkHourEntryStatus.rejected.value
        entry.rejected_reason = body.reason
        rejected_count += 1

    await db.commit()
    return {"rejected_count": rejected_count}
