"""推送反向校验端点（spec: formula-management-deep-optimization · R5）。

GET /api/formula-push/{project_id}/{year}/verify
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_project_access

router = APIRouter(prefix="/api/formula-push", tags=["formula-push-verify"])


@router.get("/{project_id}/{year}/verify")
async def verify_formula_push(
    project_id: uuid.UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("readonly")),
):
    """反向校验：对比源头值与已推送目标值的一致性。"""
    from app.services.formula_push.verify import verify_push

    return await verify_push(db, project_id, year)
