"""分析性复核底稿 — 同行业对比 + EPS-ROE 保存端点

POST /api/projects/{pid}/analytical-review/industry-comparison
POST /api/projects/{pid}/analytical-review/eps-roe
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/analytical-review",
    tags=["analytical-review"],
)


# ─── Request Models ───────────────────────────────────────────────────────────


class IndustryComparisonPayload(BaseModel):
    """同行业对比分析保存请求体"""
    companies: list[dict] = []
    financial_data: dict = {}
    comparison_table: dict = {}
    data_source_note: str = ""


class EpsRoePayload(BaseModel):
    """EPS-ROE 计算表保存请求体"""
    params: dict = {}
    share_changes: list[dict] = []
    dilution_factors: dict = {}


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/industry-comparison")
async def save_industry_comparison_endpoint(
    project_id: UUID,
    body: IndustryComparisonPayload,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """保存同行业对比分析数据（可比公司 + 财务指标 + 对比数据 + 数据来源）。"""
    from app.services.analytical_review_service import save_industry_comparison

    await save_industry_comparison(
        db, project_id, year, body.model_dump(), user_id=None
    )
    await db.commit()
    return {"status": "saved", "project_id": str(project_id), "year": year}


@router.post("/eps-roe")
async def save_eps_roe_endpoint(
    project_id: UUID,
    body: EpsRoePayload,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """保存 EPS-ROE 参数并重新计算。返回计算结果。"""
    from app.services.analytical_review_service import save_eps_roe

    computed = await save_eps_roe(
        db, project_id, year, body.model_dump(), user_id=None
    )
    await db.commit()
    return {"status": "saved", "project_id": str(project_id), "year": year, "computed": computed}
