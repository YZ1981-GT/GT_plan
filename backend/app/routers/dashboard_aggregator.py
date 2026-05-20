"""合伙人仪表盘聚合端点

Requirements: 9.1, 9.4, 9.6

提供 GET /api/projects/{project_id}/dashboard/summary 端点，
调用 DashboardAggregatorService 并发聚合全量仪表盘数据。
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_aggregator_service import DashboardAggregatorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/dashboard",
    tags=["partner-dashboard"],
)


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> DashboardSummaryResponse:
    """聚合端点：返回项目仪表盘全量数据。

    并发调用 cycle_progress / vr_summary / open_reviews / timeline / trimming，
    任一子查询失败降级为 null + errors 记录。
    """
    start_time = time.time()

    svc = DashboardAggregatorService(db)
    result = await svc.get_summary(project_id=project_id, user_id=current_user.id)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "Dashboard summary requested: project_id=%s user_id=%s elapsed=%.1fms",
        project_id,
        current_user.id,
        elapsed_ms,
    )

    # Handle project not found
    if isinstance(result, dict) and result.get("error") == "project_not_found":
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="项目不存在")

    return DashboardSummaryResponse(**result)
