"""报表分析共用的报表行来源（spec citar-report-analysis §2.2 / §2.3）。

- ``audited``：已生成的 ``financial_report``（未删除），与报表页「审定」同一来源
- ``unadjusted``：``ReportEngine.generate_unadjusted_report`` 按试算表未审数读时计算，与报表页「未审」同一路径

返回统一的 dict 行（row_code / row_name / current_period_amount / prior_period_amount /
indent_level / is_total_row），按 row_code 排序（编码三位补零，与报表页显示顺序一致）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport, FinancialReportType

VALID_MODES = ("audited", "unadjusted")


async def load_report_rows(
    db: AsyncSession, project_id: UUID, year: int, report_type: str, mode: str = "audited",
) -> list[dict[str, Any]]:
    rt = FinancialReportType(report_type)
    if mode == "unadjusted":
        from app.services.report_engine import ReportEngine

        rows = await ReportEngine(db).generate_unadjusted_report(project_id, year, rt)
        return sorted((dict(r) for r in rows), key=lambda r: str(r.get("row_code") or ""))
    if mode != "audited":
        raise ValueError(f"未知取数口径 {mode!r}，合法值：{VALID_MODES}")
    result = await db.execute(
        sa.select(FinancialReport)
        .where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.report_type == rt,
            FinancialReport.is_deleted == sa.false(),
        )
        .order_by(FinancialReport.row_code)
    )
    return [
        {
            "row_code": r.row_code,
            "row_name": r.row_name,
            "current_period_amount": r.current_period_amount,
            "prior_period_amount": r.prior_period_amount,
            "indent_level": r.indent_level or 0,
            "is_total_row": bool(r.is_total_row),
        }
        for r in result.scalars().all()
    ]
