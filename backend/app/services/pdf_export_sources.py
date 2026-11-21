"""正式 PDF 导出的真实数据来源。

当前先收口四张财务报表。该模块只读取 FinancialReport，不在 PDF 引擎里复制
报表 SQL；审计报告、附注和多文档合并仍由后续正式导出批次接入。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType

_FINANCIAL_TYPES = {
    FinancialReportType.balance_sheet.value,
    FinancialReportType.income_statement.value,
    FinancialReportType.cash_flow_statement.value,
    FinancialReportType.equity_statement.value,
}
_UNIT_LABELS = {"yuan": "元", "qian": "千元", "wan": "万元"}


class PDFSourceUnavailable(RuntimeError):
    """正式 PDF 数据来源不可用，不得用空页面冒充成功。"""

    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


async def build_financial_pdf_data(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None,
    document_types: list[str],
    unit_policy_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """从当前项目年度的 ``financial_report`` 构造非空 PDF renderer 数据。

    ``year`` 必须由任务冻结或由前端项目年度显式传入；这里不从项目名称猜年度。
    ``unit_policy_snapshot`` 是任务创建时冻结的 JSON object，PDF 数据只按该快照
    折算一次，避免项目单位在任务执行期间变化造成证据与内容分叉。
    """
    if year is None:
        raise PDFSourceUnavailable("正式 PDF 导出必须携带审计年度", status_code=422)
    if not document_types:
        raise PDFSourceUnavailable("正式 PDF 导出至少选择一份文档", status_code=422)
    unsupported = [item for item in document_types if item not in _FINANCIAL_TYPES]
    if unsupported:
        raise PDFSourceUnavailable(
            "当前批次只接入财务报表 PDF，尚未接入：" + ", ".join(unsupported)
        )
    snapshot = unit_policy_snapshot or {}
    unit = snapshot.get("unit")
    divisor = snapshot.get("divisor")
    if unit not in _UNIT_LABELS or not isinstance(divisor, int) or divisor <= 0:
        raise PDFSourceUnavailable("PDF 导出单位策略快照无效", status_code=422)

    sections: list[dict[str, Any]] = []
    for report_type in dict.fromkeys(document_types):
        enum_type = FinancialReportType(report_type)
        result = await db.execute(
            sa.select(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == enum_type,
                FinancialReport.is_deleted == sa.false(),
            )
            .order_by(FinancialReport.row_code)
        )
        source_rows = list(result.scalars().all())
        if not source_rows:
            raise PDFSourceUnavailable(
                f"项目 {project_id} 的 {year} 年 {report_type} 没有可导出的正式数据"
            )
        rows: list[dict[str, Any]] = []
        for source in source_rows:
            rows.append(
                {
                    "row_code": source.row_code,
                    "row_name": source.row_name or source.row_code,
                    "current_period_amount": _scale(source.current_period_amount, divisor),
                    "prior_period_amount": _scale(source.prior_period_amount, divisor),
                    "is_total": bool(source.is_total_row),
                    "indent_level": source.indent_level,
                }
            )
        sections.append({"report_type": report_type, "rows": rows})

    return {
        "report_type": sections[0]["report_type"] if len(sections) == 1 else "financial_report",
        "unit_label": _UNIT_LABELS[unit],
        "sections": sections,
    }


def _scale(value: Any, divisor: int) -> Decimal | None:
    if value is None:
        return None
    try:
        return (Decimal(str(value)) / Decimal(divisor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PDFSourceUnavailable("financial_report 含不可转换的金额") from exc
