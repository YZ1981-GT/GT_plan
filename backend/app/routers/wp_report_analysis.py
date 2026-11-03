"""报表分析 API 路由

GET /api/workpapers/{project_id}/{year}/full-tb
GET /api/workpapers/{project_id}/{year}/opening-reconcile
GET /api/workpapers/{project_id}/{year}/bs-trend
GET /api/workpapers/{project_id}/{year}/pl-trend
GET /api/workpapers/{project_id}/{year}/financial-ratios

Requirements: 1.x~5.x
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.core.database import get_db
from app.deps import assert_project_permission, require_project_access
from app.models.core import User
from app.services.trial_balance_full_view_service import TrialBalanceFullViewService
from app.services.report_trend_analysis_service import ReportTrendAnalysisService
from app.services.financial_ratio_service import FinancialRatioService

router = APIRouter(prefix="/api/workpapers")


@router.get("/{project_id}/{year}/full-tb")
async def get_full_tb(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> list[dict[str, Any]]:
    svc = TrialBalanceFullViewService(db)
    return await svc.get_full_view(project_id, year)


@router.get("/{project_id}/{year}/tb-balance-check")
async def check_tb_balance(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    svc = TrialBalanceFullViewService(db)
    return await svc.check_balance_formula(project_id, year)


@router.get("/{project_id}/{year}/opening-reconcile")
async def get_opening_reconcile(
    project_id: UUID, year: int,
    prior_project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> dict[str, Any]:
    if prior_project_id is not None and prior_project_id != project_id:
        # 上年审定数读的是另一个项目：同样只认项目成员（spec consol-autotree-residual-closure R2.2）
        await assert_project_permission(db, _user, prior_project_id, "readonly")
        # 上一句把 RLS 上下文设到了上年项目；后面读的仍有本项目 ⇒ 设回本项目
        await deps.set_rls_context(db, project_id)
    svc = TrialBalanceFullViewService(db)
    return await svc.reconcile_opening_balance(project_id, year, prior_project_id)


@router.get("/{project_id}/{year}/bs-trend")
async def get_bs_trend(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> list[dict[str, Any]]:
    svc = ReportTrendAnalysisService(db)
    return await svc.get_bs_trend(project_id, year, mode)


@router.get("/{project_id}/{year}/pl-trend")
async def get_pl_trend(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> list[dict[str, Any]]:
    svc = ReportTrendAnalysisService(db)
    return await svc.get_pl_trend(project_id, year, mode)


@router.get("/{project_id}/{year}/financial-ratios")
async def get_financial_ratios(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
) -> list[dict[str, Any]]:
    svc = FinancialRatioService(db)
    return await svc.calculate_ratios(project_id, year, mode)
