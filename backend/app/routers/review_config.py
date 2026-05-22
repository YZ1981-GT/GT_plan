"""复核链配置 API 路由

Phase 6 F8: 复核层级灵活化（2-4 级可配置）

GET  /api/projects/{project_id}/review-config  — 获取配置
PUT  /api/projects/{project_id}/review-config  — 更新配置

权限: manager/partner/admin 可修改
前置检查: 存在进行中复核时返回 409 禁止修改
注册到 router_registry 协作域 §104。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workpaper_models import WpReviewStatus, WorkingPaper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["review-config"])

# Default 2-level config when review_config is null
DEFAULT_REVIEW_CONFIG = {
    "levels": 2,
    "level_roles": {"L1": "manager", "L2": "partner"},
}

# Allowed roles for modification
ALLOWED_ROLES = {"manager", "partner", "admin"}

# Statuses that indicate reviews are in progress
IN_PROGRESS_STATUSES = {
    WpReviewStatus.pending_level1,
    WpReviewStatus.level1_in_progress,
    WpReviewStatus.pending_level2,
    WpReviewStatus.level2_in_progress,
    WpReviewStatus.pending_level3,
    WpReviewStatus.level3_in_progress,
    WpReviewStatus.pending_level4,
    WpReviewStatus.level4_in_progress,
}


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class ReviewConfigUpdate(BaseModel):
    levels: int
    level_roles: dict[str, str]

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, v: int) -> int:
        if v < 2 or v > 4:
            raise ValueError("levels must be between 2 and 4")
        return v

    @field_validator("level_roles")
    @classmethod
    def validate_level_roles(cls, v: dict[str, str], info) -> dict[str, str]:
        # Will be validated against levels in the endpoint
        return v


class ReviewConfigResponse(BaseModel):
    levels: int
    level_roles: dict[str, str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{project_id}/review-config")
async def get_review_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """获取项目复核链配置

    review_config=null 时返回默认 2 级配置（L1=manager, L2=partner）
    """
    # Verify project exists
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Return config or default
    if project.review_config is not None:
        return project.review_config
    return DEFAULT_REVIEW_CONFIG


@router.put("/{project_id}/review-config")
async def update_review_config(
    project_id: UUID,
    body: ReviewConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """更新复核链配置

    Requirements: F8.2, F8.3, F8.4, F8.10
    权限: 仅 manager/partner/admin 可修改
    前置检查: 存在进行中复核时返回 409
    """
    # RBAC check
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Verify project exists
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate level_roles must define L1..L{levels}
    required_keys = {f"L{i}" for i in range(1, body.levels + 1)}
    provided_keys = set(body.level_roles.keys())
    missing_keys = required_keys - provided_keys
    if missing_keys:
        raise HTTPException(
            status_code=422,
            detail=f"level_roles must define L1..L{body.levels}. Missing: {sorted(missing_keys)}",
        )

    # Pre-check: no in-progress reviews
    in_progress_count_stmt = (
        select(func.count(WorkingPaper.id))
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
            WorkingPaper.review_status.in_(IN_PROGRESS_STATUSES),
        )
    )
    count_result = await db.execute(in_progress_count_stmt)
    in_progress_count = count_result.scalar() or 0

    if in_progress_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot modify config while reviews in progress",
            headers={"X-In-Progress-Count": str(in_progress_count)},
        )

    # Update config
    new_config = {
        "levels": body.levels,
        "level_roles": body.level_roles,
    }
    project.review_config = new_config
    await db.commit()

    logger.info(
        "[REVIEW-CONFIG] project=%s user=%s updated levels=%d",
        project_id, current_user.id, body.levels,
    )

    return new_config
