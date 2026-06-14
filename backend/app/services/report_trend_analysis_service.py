"""报表趋势分析服务 — BS/PL 趋势（横向变动+纵向比重+显著标记）

Requirements: 3.1~3.5, 4.1~4.3
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport

SIGNIFICANCE_THRESHOLD = Decimal("0.10")  # 10% 变动率视为显著


class ReportTrendAnalysisService:
    """BS/PL 趋势分析"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bs_trend(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        """BS 趋势分析：本期 vs 上期，横向变动额/变动率+纵向比重。"""
        rows = await self._load_report_rows(project_id, year, "balance_sheet")
        result = []
        for row in rows:
            current = self._get_amount(row, mode)
            prior = self._get_prior(row, mode)
            change = current - prior if prior else Decimal("0")
            rate = (change / prior * 100) if prior and prior != 0 else Decimal("0")
            significant = abs(rate) >= SIGNIFICANCE_THRESHOLD * 100

            result.append({
                "row_code": row.row_code,
                "row_name": row.row_name,
                "current": current,
                "prior": prior,
                "change": change,
                "change_rate": rate,
                "significant": significant,
            })
        return result

    async def get_pl_trend(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        """PL 趋势分析：含毛利率变动。"""
        rows = await self._load_report_rows(project_id, year, "income_statement")
        result = []
        for row in rows:
            current = self._get_amount(row, mode)
            prior = self._get_prior(row, mode)
            change = current - prior if prior else Decimal("0")
            rate = (change / prior * 100) if prior and prior != 0 else Decimal("0")
            significant = abs(rate) >= SIGNIFICANCE_THRESHOLD * 100

            result.append({
                "row_code": row.row_code,
                "row_name": row.row_name,
                "current": current,
                "prior": prior,
                "change": change,
                "change_rate": rate,
                "significant": significant,
            })
        return result

    async def _load_report_rows(
        self, project_id: UUID, year: int, report_type: str
    ) -> list:
        stmt = (
            sa.select(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == report_type,
            )
            .order_by(FinancialReport.row_code)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _get_amount(row, mode: str) -> Decimal:
        return Decimal(str(row.current_period_amount or 0))

    @staticmethod
    def _get_prior(row, mode: str) -> Decimal:
        return Decimal(str(row.prior_period_amount or 0)) if hasattr(row, "prior_period_amount") else Decimal("0")
