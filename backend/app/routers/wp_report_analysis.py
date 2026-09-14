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

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.trial_balance_full_view_service import TrialBalanceFullViewService
from app.services.report_trend_analysis_service import ReportTrendAnalysisService
from app.services.financial_ratio_service import FinancialRatioService

router = APIRouter(prefix="/api/workpapers")


@router.get("/{project_id}/{year}/full-tb")
async def get_full_tb(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = TrialBalanceFullViewService(db)
    return await svc.get_full_view(project_id, year)


@router.get("/{project_id}/{year}/tb-balance-check")
async def check_tb_balance(
    project_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    svc = TrialBalanceFullViewService(db)
    return await svc.check_balance_formula(project_id, year)


@router.get("/{project_id}/{year}/opening-reconcile")
async def get_opening_reconcile(
    project_id: UUID, year: int,
    prior_project_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    svc = TrialBalanceFullViewService(db)
    return await svc.reconcile_opening_balance(project_id, year, prior_project_id)


@router.get("/{project_id}/{year}/bs-trend")
async def get_bs_trend(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = ReportTrendAnalysisService(db)
    return await svc.get_bs_trend(project_id, year, mode)


@router.get("/{project_id}/{year}/pl-trend")
async def get_pl_trend(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = ReportTrendAnalysisService(db)
    return await svc.get_pl_trend(project_id, year, mode)


@router.get("/{project_id}/{year}/financial-ratios")
async def get_financial_ratios(
    project_id: UUID, year: int,
    mode: str = Query("audited"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = FinancialRatioService(db)
    return await svc.calculate_ratios(project_id, year, mode)
