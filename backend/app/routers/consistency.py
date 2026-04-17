"""全链路一致性校验 API 路由

Phase 9 Task 9.20
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.consistency_check_service import ConsistencyCheckService

router = APIRouter(prefix="/api/projects", tags=["consistency"])


@router.get("/{project_id}/consistency-check")
async def get_consistency(
    project_id: UUID,
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取全链路一致性校验结果"""
    svc = ConsistencyCheckService(db)
    return await svc.check_full_chain(project_id, year)


@router.post("/{project_id}/consistency-check/run")
async def run_consistency(
    project_id: UUID,
    year: int = Query(2025),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """手动触发全链路校验"""
    svc = ConsistencyCheckService(db)
    result = await svc.check_full_chain(project_id, year)
    await db.commit()
    return result
