"""财务比率分析服务 — 9 个核心比率计算

Requirements: 5.1~5.5
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport


class FinancialRatioService:
    """财务比率分析"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_ratios(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        """计算 9 个核心比率（未审/已审两版）。"""
        data = await self._load_key_figures(project_id, year)

        ratios = [
            self._ratio("流动比率", data.get("current_assets"), data.get("current_liabilities"), "倍"),
            self._ratio("速动比率", data.get("quick_assets"), data.get("current_liabilities"), "倍"),
            self._ratio("资产负债率", data.get("total_liabilities"), data.get("total_assets"), "%", pct=True),
            self._ratio("毛利率", data.get("gross_profit"), data.get("revenue"), "%", pct=True),
            self._ratio("净利率", data.get("net_income"), data.get("revenue"), "%", pct=True),
            self._ratio("总资产周转率", data.get("revenue"), data.get("total_assets"), "次"),
            self._ratio("应收账款周转率", data.get("revenue"), data.get("accounts_receivable"), "次"),
            self._ratio("存货周转率", data.get("cost_of_goods"), data.get("inventory"), "次"),
            self._ratio("净资产收益率(ROE)", data.get("net_income"), data.get("equity"), "%", pct=True),
        ]
        return ratios

    async def _load_key_figures(self, project_id: UUID, year: int) -> dict[str, Decimal]:
        """从报表取关键数据行"""
        stmt = sa.select(
            FinancialReport.row_code,
            FinancialReport.current_period_amount,
        ).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
        )
        result = await self.db.execute(stmt)
        rows = {code: Decimal(str(amt or 0)) for code, amt in result.all()}

        # 映射 row_code → 语义（基于致同报表行编码）
        return {
            "current_assets": rows.get("BS-019", Decimal("0")),
            "current_liabilities": rows.get("BS-040", Decimal("0")),
            "quick_assets": rows.get("BS-019", Decimal("0")) - rows.get("BS-009", Decimal("0")),
            "total_assets": rows.get("BS-039", Decimal("0")),
            "total_liabilities": rows.get("BS-059", Decimal("0")),
            "equity": rows.get("BS-079", Decimal("0")),
            "revenue": rows.get("PL-001", Decimal("0")),
            "cost_of_goods": rows.get("PL-002", Decimal("0")),
            "gross_profit": rows.get("PL-001", Decimal("0")) - rows.get("PL-002", Decimal("0")),
            "net_income": rows.get("PL-030", Decimal("0")),
            "accounts_receivable": rows.get("BS-004", Decimal("0")),
            "inventory": rows.get("BS-009", Decimal("0")),
        }

    @staticmethod
    def _ratio(
        name: str, numerator: Decimal | None, denominator: Decimal | None, unit: str, pct: bool = False
    ) -> dict[str, Any]:
        num = numerator or Decimal("0")
        den = denominator or Decimal("0")
        if den == 0:
            return {"name": name, "value": None, "unit": unit, "abnormal": False, "note": "分母为零"}
        value = (num / den * 100) if pct else (num / den)
        # 异常判定简化规则
        abnormal = False
        if "负债率" in name and value > Decimal("70"):
            abnormal = True
        if "流动比率" in name and value < Decimal("1"):
            abnormal = True
        return {"name": name, "value": round(value, 2), "unit": unit, "abnormal": abnormal, "note": ""}
