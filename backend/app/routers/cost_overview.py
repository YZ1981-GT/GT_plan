"""成本看板端点 — Round 2 需求 9

GET /api/projects/{project_id}/cost-overview
返回 burn rate / 超支预计 / 按角色成本分布
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services import cost_overview_service

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["cost-overview"],
)


@router.get("/cost-overview")
async def get_cost_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    """获取项目成本概览。

    返回:
        budget_hours, actual_hours, remaining_hours, burn_rate_per_day,
        projected_overrun_date, contract_amount, cost_by_role
    """
    return await cost_overview_service.compute(db=db, project_id=project_id)
