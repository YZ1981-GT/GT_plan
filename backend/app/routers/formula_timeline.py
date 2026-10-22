"""公式版本时间轴端点（spec: formula-management-deep-optimization · R6）。

GET /api/formula-timeline/{project_id}/{year}
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_project_access

router = APIRouter(prefix="/api/formula-timeline", tags=["formula-timeline"])


@router.get("/{project_id}/{year}")
async def get_formula_timeline(
    project_id: uuid.UUID,
    year: int,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("readonly")),
):
    """返回项目公式版本时间轴（聚合五数据源，按时间倒序）。"""
    from app.services.formula_timeline_service import build_timeline

    return await build_timeline(db, project_id, year, limit=limit)
