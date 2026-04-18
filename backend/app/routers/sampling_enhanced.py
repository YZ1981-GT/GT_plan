"""抽样程序增强 API — Phase 10 Task 6.1-6.4"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sampling_enhanced_service import (
    AgingAnalysisService,
    CutoffTestService,
    MonthlyDetailService,
)

router = APIRouter(prefix="/api/projects", tags=["sampling-enhanced"])


# ── Schemas ───────────────────────────────────────────────

class CutoffTestRequest(BaseModel):
    account_codes: list[str]
    year: int
    days_before: int = 5
    days_after: int = 5
    amount_threshold: float = 10000


class AgingBracket(BaseModel):
    label: str
    min_days: int = 0
    max_days: int | None = None


class AgingAnalysisRequest(BaseModel):
    account_code: str
    aging_brackets: list[AgingBracket]
    base_date: str
    year: int | None = None


class MonthlyDetailRequest(BaseModel):
    account_code: str
    year: int


# ── 截止性测试 ────────────────────────────────────────────

@router.post("/{project_id}/sampling/cutoff-test")
async def cutoff_test(
    project_id: UUID,
    req: CutoffTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """截止性测试 — 提取期末前后 N 天交易"""
    svc = CutoffTestService()
    return await svc.run_cutoff_test(
        db, project_id, req.year, req.account_codes,
        req.days_before, req.days_after, req.amount_threshold,
    )


# ── 账龄分析 ──────────────────────────────────────────────

@router.post("/{project_id}/sampling/aging-analysis")
async def aging_analysis(
    project_id: UUID,
    req: AgingAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    """账龄分析 — FIFO 先进先出核销"""
    svc = AgingAnalysisService()
    brackets = [b.model_dump() for b in req.aging_brackets]
    return await svc.analyze_aging(
        db, project_id, req.account_code, brackets, req.base_date, req.year,
    )


# ── 月度明细 ──────────────────────────────────────────────

@router.post("/{project_id}/sampling/monthly-detail")
async def monthly_detail(
    project_id: UUID,
    req: MonthlyDetailRequest,
    db: AsyncSession = Depends(get_db),
):
    """月度明细填充 — 按月汇总序时账"""
    svc = MonthlyDetailService()
    return await svc.generate_monthly_detail(
        db, project_id, req.account_code, req.year,
    )
