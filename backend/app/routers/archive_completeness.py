"""归档前完整性自检报告路由

Requirements: 3.1, 3.2

GET /api/projects/{project_id}/archive-completeness-report
返回 CompletenessReportResponse（categories + can_proceed + generated_at）。
注册到 router_registry 协作域 §99。
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
from app.services.archive_completeness_service import (
    CompletenessReportResponse,
    get_archive_completeness_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/archive-completeness-report",
    tags=["archive-completeness"],
)


@router.get("", response_model=CompletenessReportResponse)
async def get_completeness_report(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
) -> CompletenessReportResponse:
    """获取归档前完整性自检报告。

    四类检查：缺失底稿 / 未签字底稿 / 未解决复核意见 / stale 底稿。
    can_proceed = True 当且仅当无 blocking 类别有 count > 0。
    """
    start_time = time.time()

    result = await get_archive_completeness_report(db=db, project_id=project_id)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "Archive completeness report: project=%s user=%s can_proceed=%s elapsed=%.1fms",
        project_id,
        current_user.id,
        result.can_proceed,
        elapsed_ms,
    )

    return result
