# -*- coding: utf-8 -*-
"""合伙人轮换检查 API

Refinement Round 1 — 需求 11：
GET /api/rotation/check?staff_id=&client_name= 返回连续年数。
POST /api/rotation/overrides 创建 override 申请。
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.rotation_models import PartnerRotationOverride
from app.services.rotation_check_service import RotationCheckService

router = APIRouter(prefix="/rotation", tags=["轮换检查"])


@router.get("/check")
async def check_rotation(
    staff_id: UUID = Query(..., description="人员 ID"),
    client_name: str = Query(..., description="客户名称"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查指定人员对指定客户的连续审计年数。

    返回:
        - continuous_years: 连续审计年数
        - next_rotation_due_year: 下次轮换到期年份
        - current_override_id: 当前有效的 override ID（如有）
        - rotation_limit: 轮换上限年数
    """
    svc = RotationCheckService(db)
    return await svc.check_rotation(staff_id=staff_id, client_name=client_name)


class OverrideCreateRequest(BaseModel):
    staff_id: UUID
    client_name: str
    original_years: int
    override_reason: str


@router.post("/overrides")
async def create_rotation_override(
    body: OverrideCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建轮换 override 申请。

    创建后需合规合伙人 + 首席风控合伙人双签（通过 SignatureRecord 机制，
    object_type='rotation_override'）。本端点仅创建记录，双签由签字流程完成。
    """
    override = PartnerRotationOverride(
        id=uuid4(),
        staff_id=body.staff_id,
        client_name=body.client_name,
        original_years=body.original_years,
        override_reason=body.override_reason,
        approved_by_compliance_partner=None,
        approved_by_chief_risk_partner=None,
        override_expires_at=None,
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)

    return {
        "id": str(override.id),
        "staff_id": str(override.staff_id),
        "client_name": override.client_name,
        "original_years": override.original_years,
        "override_reason": override.override_reason,
        "approved_by_compliance_partner": None,
        "approved_by_chief_risk_partner": None,
        "override_expires_at": None,
        "created_at": override.created_at.isoformat() if override.created_at else None,
    }
