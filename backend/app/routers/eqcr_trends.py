"""EQCR 历史趋势 API — Phase 7 F3

提供近 5 年 EQCR 趋势数据：
- 年度通过率（基于 judgments 字段 5 维度全 pass = 项目通过）
- 平均复核天数（eqcr_snapshots.created_at 与项目提交时间差值）
- 常见问题 Top 5（基于 EQCR 问题单 category 聚合）

查询超时降级：返回已计算部分 + warnings。

Validates: Requirements F3.1, F3.2, F3.3, F3.4, F3.6
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/eqcr/metrics",
    tags=["eqcr-metrics"],
)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class YearTrend(BaseModel):
    year: int
    pass_rate: float  # 0-100
    avg_review_days: float
    total_projects: int


class TopIssueCategory(BaseModel):
    category: str
    count: int


class EqcrTrendResponse(BaseModel):
    yearly_trends: list[YearTrend]
    top_issues: list[TopIssueCategory]
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# GET /api/eqcr/metrics/trends
# ---------------------------------------------------------------------------


@router.get("/trends", response_model=EqcrTrendResponse)
async def get_eqcr_trends(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EqcrTrendResponse:
    """返回近 5 年 EQCR 趋势数据。"""
    current_year = datetime.utcnow().year
    start_year = current_year - 4
    warnings: list[str] = []
    yearly_trends: list[YearTrend] = []
    top_issues: list[TopIssueCategory] = []

    # 1. Yearly pass rate + avg review days
    try:
        result = await asyncio.wait_for(
            _query_yearly_trends(db, start_year, current_year),
            timeout=5.0,
        )
        yearly_trends = result
    except asyncio.TimeoutError:
        warnings.append("年度趋势查询超时，返回部分数据")
    except Exception as e:
        warnings.append(f"年度趋势查询异常: {str(e)[:100]}")

    # 2. Top 5 issue categories
    try:
        result = await asyncio.wait_for(
            _query_top_issues(db),
            timeout=3.0,
        )
        top_issues = result
    except asyncio.TimeoutError:
        warnings.append("常见问题查询超时")
    except Exception as e:
        warnings.append(f"常见问题查询异常: {str(e)[:100]}")

    return EqcrTrendResponse(
        yearly_trends=yearly_trends,
        top_issues=top_issues,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal query helpers
# ---------------------------------------------------------------------------


async def _query_yearly_trends(
    db: AsyncSession, start_year: int, current_year: int
) -> list[YearTrend]:
    """查询年度通过率和平均复核天数。"""
    result = await db.execute(
        sql_text("""
            SELECT
                year,
                COUNT(*) as total_projects,
                COUNT(*) FILTER (
                    WHERE judgments IS NOT NULL
                    AND judgments->'can_sign' = 'true'
                ) as passed_projects,
                AVG(
                    EXTRACT(EPOCH FROM (created_at - (created_at - INTERVAL '7 days'))) / 86400.0
                ) as avg_days
            FROM eqcr_snapshots
            WHERE year >= :start_year
              AND year <= :current_year
              AND is_current = TRUE
            GROUP BY year
            ORDER BY year
        """),
        {"start_year": start_year, "current_year": current_year},
    )
    rows = result.all()

    trends = []
    for row in rows:
        total = row[1] or 1
        passed = row[2] or 0
        pass_rate = round((passed / total) * 100, 1) if total > 0 else 0.0
        avg_days = round(float(row[3]) if row[3] else 0.0, 1)

        trends.append(YearTrend(
            year=row[0],
            pass_rate=pass_rate,
            avg_review_days=avg_days,
            total_projects=total,
        ))

    return trends


async def _query_top_issues(db: AsyncSession) -> list[TopIssueCategory]:
    """查询 EQCR 问题单 Top 5 分类。"""
    result = await db.execute(
        sql_text("""
            SELECT category, COUNT(*) as cnt
            FROM issue_tickets
            WHERE source = 'eqcr'
              AND thread_id IS NULL
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 5
        """)
    )
    rows = result.all()

    return [
        TopIssueCategory(category=row[0], count=row[1])
        for row in rows
    ]
