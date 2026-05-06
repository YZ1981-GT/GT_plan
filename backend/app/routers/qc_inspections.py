"""QC 抽查路由 — Round 3 需求 4

POST   /api/qc/inspections                         — 创建抽查批次
GET    /api/qc/inspections                         — 列出抽查批次
GET    /api/qc/inspections/{id}                    — 获取抽查详情
POST   /api/qc/inspections/{id}/items/{item_id}/verdict — 录入结论

权限：role='qc' | 'admin'
"""

from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.qc_inspection_service import qc_inspection_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc/inspections", tags=["qc-inspections"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateInspectionRequest(BaseModel):
    """创建抽查批次请求体"""

    project_id: UUID = Field(..., description="项目 ID")
    strategy: Literal["random", "risk_based", "full_cycle", "mixed"] = Field(
        ..., description="抽样策略"
    )
    params: Optional[dict] = Field(
        None,
        description="策略参数，如 {ratio: 0.1} / {cycles: ['D']} / {random_ratio: 0.2, cycles: ['D']}",
    )
    reviewer_id: UUID = Field(..., description="质控复核人 ID")


class VerdictRequest(BaseModel):
    """录入结论请求体"""

    verdict: Literal["pass", "fail", "conditional_pass"] = Field(
        ..., description="结论: pass / fail / conditional_pass"
    )
    findings: Optional[dict] = Field(
        None, description="发现的问题（JSONB）"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_inspection(
    body: CreateInspectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """创建质控抽查批次，按策略生成抽查子项。"""
    result = await qc_inspection_service.create_inspection(
        db,
        project_id=body.project_id,
        strategy=body.strategy,
        params=body.params,
        reviewer_id=body.reviewer_id,
    )
    await db.commit()
    return result


@router.get("")
async def list_inspections(
    project_id: Optional[UUID] = Query(None, description="按项目过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """列出质控抽查批次。"""
    return await qc_inspection_service.list_inspections(
        db,
        project_id=project_id,
        page=page,
        page_size=page_size,
    )


@router.get("/{inspection_id}")
async def get_inspection(
    inspection_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """获取抽查批次详情（含子项）。"""
    return await qc_inspection_service.get_inspection(db, inspection_id)


@router.post("/{inspection_id}/items/{item_id}/verdict")
async def record_verdict(
    inspection_id: UUID,
    item_id: UUID,
    body: VerdictRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin"])),
):
    """QC 复核人录入结论（pass / fail / conditional_pass）。"""
    result = await qc_inspection_service.record_verdict(
        db,
        inspection_id=inspection_id,
        item_id=item_id,
        verdict=body.verdict,
        findings=body.findings,
    )
    await db.commit()
    return result
