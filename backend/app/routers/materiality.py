"""重要性水平 API

覆盖：
- GET  获取当前重要性水平
- POST calculate 计算
- PUT  override 手动覆盖
- GET  history 变更历史
- GET  benchmark 自动取基准金额
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_schemas import (
    MaterialityInput,
    MaterialityOverride,
)
from app.services.materiality_service import MaterialityService

router = APIRouter(
    prefix="/api/projects/{project_id}/materiality",
    tags=["materiality"],
)


@router.get("")
async def get_materiality(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取当前重要性水平"""
    svc = MaterialityService(db)
    result = await svc.get_current(project_id, year)
    if not result:
        return None
    return result.model_dump()


@router.post("/calculate")
async def calculate_materiality(
    project_id: UUID,
    year: int = Query(...),
    params: MaterialityInput = ...,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """计算重要性水平"""
    svc = MaterialityService(db)
    result = await svc.calculate(project_id, year, params, user.id)
    await db.commit()
    return result.model_dump()


@router.put("/override")
async def override_materiality(
    project_id: UUID,
    year: int = Query(...),
    overrides: MaterialityOverride = ...,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """手动覆盖重要性水平"""
    svc = MaterialityService(db)
    try:
        result = await svc.override(project_id, year, overrides, user.id)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
async def get_history(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """变更历史"""
    svc = MaterialityService(db)
    changes = await svc.get_change_history(project_id, year)
    return [c.model_dump() for c in changes]


@router.get("/benchmark")
async def get_benchmark(
    project_id: UUID,
    year: int = Query(...),
    benchmark_type: str = Query(...),
    company_code: str = Query("001"),
    db: AsyncSession = Depends(get_db),
):
    """从试算表自动取基准金额"""
    svc = MaterialityService(db)
    try:
        amount = await svc.auto_populate_benchmark(
            project_id, year, benchmark_type, company_code
        )
        return {"benchmark_type": benchmark_type, "benchmark_amount": str(amount)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
