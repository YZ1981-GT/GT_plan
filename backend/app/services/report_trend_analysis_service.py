"""报表变动分析服务 — 资产负债表 / 利润表本期对上期（spec citar-report-analysis §2.3）。

- ``mode`` 生效：审定读已生成报表，未审读按试算表未审数计算的报表（``report_analysis_rows``）
- 上期为空或 0 时变动率为 ``None``（不写 0 冒充「没变动」）
- 变动率绝对值 ≥ 10% 标显著

Requirements: 3.1~3.5, 4.1~4.3
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.report_analysis_rows import load_report_rows

SIGNIFICANCE_THRESHOLD = Decimal("0.10")  # 10% 变动率视为显著


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - 非法金额按缺失处理
        return None


def build_trend_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """报表行 → 变动分析行（纯函数，单测直接调用）。"""
    result = []
    for row in rows:
        current = _dec(row.get("current_period_amount"))
        prior = _dec(row.get("prior_period_amount"))
        change = (current or Decimal("0")) - prior if prior is not None else None
        rate = None
        if change is not None and prior != 0:
            rate = (change / abs(prior) * 100).quantize(Decimal("0.01"))
        result.append({
            "row_code": row.get("row_code"),
            "row_name": row.get("row_name"),
            "indent_level": row.get("indent_level") or 0,
            "is_total_row": bool(row.get("is_total_row")),
            "current": current,
            "prior": prior,
            "change": change,
            "change_rate": rate,
            "significant": rate is not None and abs(rate) >= SIGNIFICANCE_THRESHOLD * 100,
        })
    return result


class ReportTrendAnalysisService:
    """资产负债表 / 利润表变动分析"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bs_trend(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        rows = await load_report_rows(self.db, project_id, year, "balance_sheet", mode)
        return build_trend_rows(rows)

    async def get_pl_trend(
        self, project_id: UUID, year: int, mode: str = "audited"
    ) -> list[dict[str, Any]]:
        rows = await load_report_rows(self.db, project_id, year, "income_statement", mode)
        return build_trend_rows(rows)
