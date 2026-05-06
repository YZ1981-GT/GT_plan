"""EQCR 影子计算端点"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_shadow_compute_service import (
    ALLOWED_COMPUTATION_TYPES,
    EqcrShadowComputeService,
)

from .schemas import ShadowComputeRequest

router = APIRouter()


@router.post("/shadow-compute")
async def eqcr_shadow_compute(
    payload: ShadowComputeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 影子计算：独立跑一遍勾稽，不依赖项目组结果。"""
    if payload.computation not in ALLOWED_COMPUTATION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"computation 不合法，允许值：{sorted(ALLOWED_COMPUTATION_TYPES)}",
        )

    redis_client = None
    try:
        from app.core.redis import redis_client as _redis
        await _redis.ping()
        redis_client = _redis
    except Exception:
        pass

    svc = EqcrShadowComputeService(db)
    allowed, remaining = await svc.check_rate_limit(payload.project_id, redis_client)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "影子计算限流：每项目每天最多 20 次",
                "project_id": str(payload.project_id),
                "daily_limit": 20,
                "remaining": 0,
            },
            headers={"Retry-After": "86400"},
        )

    result = await svc.execute_shadow_compute(
        project_id=payload.project_id,
        computation_type=payload.computation,
        params=payload.params,
        user_id=current_user.id,
    )
    await db.commit()
    return result


@router.get("/projects/{project_id}/shadow-computations")
async def list_shadow_computations(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回该项目所有影子计算记录列表。"""
    svc = EqcrShadowComputeService(db)
    return await svc.list_shadow_computations(project_id)
