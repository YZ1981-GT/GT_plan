"""Phase 14: SoD 职责分离校验路由

对齐 v2 WP-ENT-04: POST /api/sod/check
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.sod_guard_service import sod_guard_service

router = APIRouter(prefix="/sod", tags=["SoDGuard"])


class SoDCheckRequest(BaseModel):
    project_id: uuid.UUID
    wp_id: uuid.UUID
    actor_id: uuid.UUID
    target_role: str  # preparer/reviewer/partner_approver/qc_reviewer


class SoDCheckResponse(BaseModel):
    allowed: bool
    conflict_type: str = None
    policy_code: str = None
    trace_id: str


@router.post("/check", response_model=SoDCheckResponse)
async def check_sod(
    req: SoDCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验 SoD 职责分离冲突

    冲突时返回 403 + conflict_type + policy_code
    """
    result = await sod_guard_service.check(
        db=db,
        project_id=req.project_id,
        wp_id=req.wp_id,
        actor_id=req.actor_id,
        target_role=req.target_role,
    )

    if not result.allowed:
        raise HTTPException(status_code=403, detail={
            "error_code": "SOD_CONFLICT_DETECTED",
            "message": result.conflict_type,
            "policy_code": result.policy_code,
            "trace_id": result.trace_id,
        })

    return SoDCheckResponse(
        allowed=True,
        trace_id=result.trace_id,
    )
