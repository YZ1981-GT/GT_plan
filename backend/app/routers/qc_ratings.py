"""QC 评级路由 — Round 3 需求 3, 6, 7

GET  /api/qc/projects/{project_id}/rating/{year}           — 获取项目评级
POST /api/qc/projects/{project_id}/rating/{year}/override  — 人工覆盖评级
POST /api/qc/ratings/compute                               — 手动触发全所计算（admin）
GET  /api/qc/reviewer-metrics                              — 复核人深度指标
GET  /api/qc/clients/{client_name}/quality-trend           — 客户质量趋势

权限：role='qc' | 'admin' | 'partner'
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User
from app.services.quality_rating_service import quality_rating_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qc", tags=["qc-ratings"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class OverrideRatingRequest(BaseModel):
    """人工覆盖评级请求体"""

    rating: str = Field(
        ..., pattern="^[ABCD]$", description="覆盖评级: A/B/C/D"
    )
    reason: str = Field(
        ..., min_length=1, description="覆盖原因（必须附文字说明）"
    )


class ComputeRatingsRequest(BaseModel):
    """手动触发评级计算请求体"""

    year: int = Field(..., ge=2020, le=2099, description="计算年份")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/rating/{year}")
async def get_project_rating(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin", "partner"])),
):
    """获取项目评级 + 各维度得分 + 推导过程（透明性）。

    需求 3.4: GET /api/qc/projects/{project_id}/rating/{year}
    返回评级 + 各维度得分 + 推导过程。
    """
    result = await quality_rating_service.get_rating(db, project_id, year)
    if not result:
        raise HTTPException(
            status_code=404, detail="该项目该年度暂无评级记录"
        )
    return result


@router.post("/projects/{project_id}/rating/{year}/override")
async def override_project_rating(
    project_id: UUID,
    year: int,
    body: OverrideRatingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin", "partner"])),
):
    """人工覆盖评级（必须附文字说明）。

    需求 3.5: 质控可人工 override 评级，override 必须附文字说明，
    系统并存系统评级与人工评级。
    """
    try:
        result = await quality_rating_service.override_rating(
            db,
            project_id=project_id,
            year=year,
            rating=body.rating,
            reason=body.reason,
            override_by=current_user.id,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ratings/compute")
async def compute_all_ratings(
    body: ComputeRatingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """手动触发全所评级计算（仅 admin）。

    通常由定时任务每月 1 日自动执行，此端点用于手动补算。
    """
    count = await quality_rating_service.compute_all_projects(db, body.year)
    await db.commit()
    return {
        "message": f"已完成 {count} 个项目的评级计算",
        "year": body.year,
        "computed_count": count,
    }


# ---------------------------------------------------------------------------
# 复核人深度指标（需求 6）
# ---------------------------------------------------------------------------


@router.get("/reviewer-metrics")
async def get_reviewer_metrics(
    year: int | None = Query(None, ge=2020, le=2099, description="年份"),
    reviewer_id: UUID | None = Query(None, description="复核人 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin", "partner"])),
):
    """获取复核人深度指标。

    需求 6.1: GET /api/qc/reviewer-metrics?year=&reviewer_id=
    返回 avg_review_time_min / avg_comments_per_wp / rejection_rate /
    qc_rule_catch_rate / sampled_rework_rate。

    返回每个复核人最新的快照记录。
    """
    from app.services.reviewer_metrics_service import reviewer_metrics_service

    results = await reviewer_metrics_service.get_metrics(
        db, reviewer_id=reviewer_id, year=year
    )
    return {"items": results, "total": len(results)}


# ---------------------------------------------------------------------------
# 客户质量趋势（需求 7）
# ---------------------------------------------------------------------------


@router.get("/clients/{client_name}/quality-trend")
async def get_client_quality_trend(
    client_name: str,
    years: int = Query(3, ge=1, le=10, description="查询年数（默认 3）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["qc", "admin", "partner"])),
):
    """获取客户近 N 年质量趋势。

    需求 7.1: GET /api/qc/clients/{client_name}/quality-trend?years=3
    返回近 N 年该客户所有项目的评级、问题数、错报金额、重要性水平变化。

    需求 7.3: 客户串联用 client_name 精确匹配。
    需求 7.4: 缺失年份返回 {year: YYYY, data: null}，不报错。
    """
    from app.services.client_quality_trend_service import (
        client_quality_trend_service,
    )

    result = await client_quality_trend_service.get_quality_trend(
        db, client_name=client_name, years=years
    )
    return result
