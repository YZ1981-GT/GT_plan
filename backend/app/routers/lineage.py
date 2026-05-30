"""统一溯源端点 — wp-traceability-panel Task 1.2

GET /api/projects/{pid}/lineage?object_type=...&object_id=...&direction=...

Requirements: 1.1, 1.2, 1.3
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_project_access
from app.models.core import User
from app.services.unified_lineage_service import UnifiedLineageService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/lineage",
    tags=["lineage"],
)


@router.get("")
async def get_lineage(
    project_id: UUID,
    object_type: Literal["wp_cell", "report_row", "note_cell", "tb_row", "adjustment"] = Query(
        ..., description="对象类型"
    ),
    object_id: str = Query(..., description="对象标识（wp_code / section_number / row_code）"),
    direction: Literal["both", "upstream", "downstream"] = Query(
        default="both", description="溯源方向"
    ),
    year: int | None = Query(default=None, description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """统一溯源查询：返回 upstream / downstream / current（LocateTarget 格式）+ 关联附件列表。"""
    svc = UnifiedLineageService(db)
    result = await svc.query_lineage(
        project_id=project_id,
        object_type=object_type,
        object_id=object_id,
        direction=direction,
        year=year,
    )
    return result
