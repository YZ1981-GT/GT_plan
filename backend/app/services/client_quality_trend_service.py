"""客户质量趋势服务 — Round 3 需求 7

按 client_name 精确匹配聚合近 N 年评级/问题数/错报金额/重要性水平。
缺失年份返回空槽 {year: YYYY, data: null} 不报错。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import UnadjustedMisstatement
from app.models.core import Project
from app.models.phase15_models import IssueTicket
from app.models.qc_rating_models import ProjectQualityRating

logger = logging.getLogger(__name__)


class ClientQualityTrendService:
    """客户质量趋势聚合服务。

    按 client_name 精确匹配查找该客户所有项目，
    聚合近 N 年的评级、问题数、错报金额、重要性水平变化。
    """

    async def get_quality_trend(
        self,
        db: AsyncSession,
        client_name: str,
        years: int = 3,
    ) -> dict:
        """获取客户近 N 年质量趋势。

        Args:
            db: 数据库会话
            client_name: 客户名称（精确匹配）
            years: 查询年数（默认 3）

        Returns:
            {
                client_name: str,
                years_requested: int,
                trend: [
                    {year: 2024, data: {...}} | {year: 2024, data: null},
                    ...
                ]
            }
        """
        current_year = datetime.now(timezone.utc).year
        year_range = list(range(current_year - years + 1, current_year + 1))

        # 1. 查找该客户所有项目 ID
        project_stmt = select(Project.id).where(
            Project.client_name == client_name,
            Project.is_deleted == False,  # noqa: E712
        )
        project_result = await db.execute(project_stmt)
        project_ids = [row[0] for row in project_result.all()]

        if not project_ids:
            # 客户无任何项目，所有年份返回空槽
            return {
                "client_name": client_name,
                "years_requested": years,
                "trend": [{"year": y, "data": None} for y in year_range],
            }

        # 使用子查询形式（避免 IN 列表的 UUID 类型兼容问题）
        project_id_subq = select(Project.id).where(
            Project.client_name == client_name,
            Project.is_deleted == False,  # noqa: E712
        )

        # 2. 批量查询各年评级
        ratings_by_year = await self._get_ratings_by_year(
            db, project_id_subq, year_range
        )

        # 3. 批量查询各年问题数
        issues_by_year = await self._get_issue_counts_by_year(
            db, project_id_subq, year_range
        )

        # 4. 批量查询各年错报金额
        misstatements_by_year = await self._get_misstatement_totals_by_year(
            db, project_id_subq, year_range
        )

        # 5. 批量查询各年重要性水平
        materiality_by_year = await self._get_materiality_by_year(
            db, client_name, year_range
        )

        # 6. 组装结果
        trend = []
        for y in year_range:
            rating_info = ratings_by_year.get(y)
            issue_count = issues_by_year.get(y, 0)
            misstatement_total = misstatements_by_year.get(y, Decimal("0"))
            materiality = materiality_by_year.get(y)

            # 判断该年是否有数据（至少有评级或有项目活动）
            has_data = (
                rating_info is not None
                or issue_count > 0
                or misstatement_total > 0
                or materiality is not None
            )

            if has_data:
                trend.append({
                    "year": y,
                    "data": {
                        "rating": rating_info.get("rating") if rating_info else None,
                        "score": rating_info.get("score") if rating_info else None,
                        "issue_count": issue_count,
                        "misstatement_amount": float(misstatement_total),
                        "materiality_level": materiality,
                        "project_count": rating_info.get("project_count", 0) if rating_info else 0,
                    },
                })
            else:
                trend.append({"year": y, "data": None})

        return {
            "client_name": client_name,
            "years_requested": years,
            "trend": trend,
        }

    async def _get_ratings_by_year(
        self,
        db: AsyncSession,
        project_id_subq,
        year_range: list[int],
    ) -> dict:
        """查询各年评级（取最差评级作为客户年度代表）。"""
        stmt = (
            select(
                ProjectQualityRating.year,
                func.count(ProjectQualityRating.id).label("project_count"),
                # 取最差评级（D > C > B > A）
                func.max(ProjectQualityRating.rating).label("worst_rating"),
                func.avg(ProjectQualityRating.score).label("avg_score"),
            )
            .where(
                ProjectQualityRating.project_id.in_(project_id_subq),
                ProjectQualityRating.year.in_(year_range),
            )
            .group_by(ProjectQualityRating.year)
        )
        result = await db.execute(stmt)
        rows = result.all()

        ratings_by_year = {}
        for row in rows:
            ratings_by_year[row.year] = {
                "rating": row.worst_rating,
                "score": round(float(row.avg_score), 1) if row.avg_score else None,
                "project_count": row.project_count,
            }
        return ratings_by_year

    async def _get_issue_counts_by_year(
        self,
        db: AsyncSession,
        project_id_subq,
        year_range: list[int],
    ) -> dict[int, int]:
        """查询各年问题数（按 created_at 年份分组）。"""
        stmt = (
            select(
                func.extract("year", IssueTicket.created_at).label("yr"),
                func.count(IssueTicket.id).label("cnt"),
            )
            .where(
                IssueTicket.project_id.in_(project_id_subq),
                func.extract("year", IssueTicket.created_at).in_(year_range),
            )
            .group_by(func.extract("year", IssueTicket.created_at))
        )
        result = await db.execute(stmt)
        rows = result.all()
        return {int(row.yr): row.cnt for row in rows}

    async def _get_misstatement_totals_by_year(
        self,
        db: AsyncSession,
        project_id_subq,
        year_range: list[int],
    ) -> dict[int, Decimal]:
        """查询各年错报金额合计。"""
        stmt = (
            select(
                UnadjustedMisstatement.year,
                func.sum(func.abs(UnadjustedMisstatement.misstatement_amount)).label(
                    "total"
                ),
            )
            .where(
                UnadjustedMisstatement.project_id.in_(project_id_subq),
                UnadjustedMisstatement.year.in_(year_range),
                UnadjustedMisstatement.is_deleted == False,  # noqa: E712
            )
            .group_by(UnadjustedMisstatement.year)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return {row.year: row.total or Decimal("0") for row in rows}

    async def _get_materiality_by_year(
        self,
        db: AsyncSession,
        client_name: str,
        year_range: list[int],
    ) -> dict[int, float | None]:
        """查询各年重要性水平（按 audit_period_end 年份分组，取最新）。"""
        stmt = (
            select(
                func.extract("year", Project.audit_period_end).label("yr"),
                func.max(Project.materiality_level).label("materiality"),
            )
            .where(
                Project.client_name == client_name,
                Project.is_deleted == False,  # noqa: E712
                Project.audit_period_end.isnot(None),
                func.extract("year", Project.audit_period_end).in_(year_range),
            )
            .group_by(func.extract("year", Project.audit_period_end))
        )
        result = await db.execute(stmt)
        rows = result.all()
        return {
            int(row.yr): float(row.materiality) if row.materiality else None
            for row in rows
        }


# 模块级单例
client_quality_trend_service = ClientQualityTrendService()
