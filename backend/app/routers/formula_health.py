"""项目级公式健康度端点（spec: formula-management-deep-optimization · R2）。

GET /api/formula-health/{project_id}/{year}
返回六维度聚合指标，供公式看板「项目健康度」面板消费。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(prefix="/api/formula-health", tags=["formula-health"])


@router.get("/{project_id}/{year}")
async def get_formula_health(
    project_id: uuid.UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("readonly")),
):
    """返回项目公式健康度六维度指标。"""
    from app.services.formula_health_service import compute_health

    return await compute_health(db, project_id, year)
