"""
单张报表 Excel 正式导出（从 `routers/reports.py` 抽出）。

## 为什么单独成文件

`routers/reports.py` 已在文件行数门白名单（基线 839 行、上限 881）。
接入 ExportUnitPolicy 后行数超限，按项目纪律**「超限优先抽模块不抬白名单」**
把导出实现整段抽出来。

## 单位口径（spec platform-global-display-settings-closure 任务 10 / AC-20）

本端点已在 `EXPORT_SURFACE_REGISTRY` 登记为 `formal`，因此必须：

1. 经唯一入口 `resolve_export_policy` 取项目 policy（**不读 displayPrefs**）；
2. 金额按 `policy.divisor` 折算（Decimal `ROUND_HALF_UP` 到 0.01）；
3. 写「金额单位：X」标注 —— **数值与标注同源**；
4. 不写 `_GT_EXPORT_META`（那是 `data_exchange` 的标记，`formal` 不得有）。

🔴 修前状态（2026-11-16 浏览器实测抓到的真实缺陷）：本端点直接写
`current_period_amount` 原值、无单位标注 ⇒ 项目单位设成万元时，
yuan 与 wan 两档导出的 xlsx **sha256 完全相同**，用户按万元看数、
拿到的却是元值。这正是本 spec 要消灭的那类错。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from typing import Any
from urllib.parse import quote
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport, FinancialReportType
from app.services.export_unit_policy_resolver import resolve_export_policy
from app.services.report_freshness import (
    definition_hash_for,
    formula_for,
    load_effective_formula_state,
    row_status,
    status_note,
)

#: 正式导出单位的中文标签（与 `report_body_service._UNIT_LABELS` 同一口径）。
EXPORT_UNIT_LABELS: dict[str, str] = {
    "yuan": "元",
    "qian": "千元",
    "wan": "万元",
}


def convert_amount_for_export(value: Any, divisor: int) -> float | None:
    """按导出 policy 的 divisor 折算一个金额单元格。

    四条纪律（与 `trial_balance_export` / `report_body_service` 同一套）：

    1. `None` / 空串返回 `None`（缺数 ≠ 零，不写 0 冒充有数据）；
    2. `divisor == 1`（元）不做量化（`1234.5` 不变成 `1234.50`）；
    3. 有限 Decimal 走 `value / divisor` + `ROUND_HALF_UP` 到 0.01；
    4. 非法 / 非有限值**抛**（不静默写 0 —— 那会让用户以为该行真的是 0）。

    返回 `float` 是因为 openpyxl 直接写 float 最稳（Decimal 会被存成字符串，
    下游按数值排序 / 求和就失效了）。
    """
    if value is None or value == "":
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"报表金额无法解析为数值：{value!r}",
        ) from exc
    if not dec.is_finite():
        raise HTTPException(status_code=500, detail=f"报表金额非有限值：{value!r}")
    if divisor == 1:
        return float(dec)
    converted = (dec / Decimal(divisor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(converted)


async def build_report_excel_response(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    report_type: FinancialReportType,
) -> StreamingResponse:
    """构造单张报表的正式 Excel 响应（含单位标注与折算）。"""
    rows = (
        await db.execute(
            sa.select(FinancialReport)
            .where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == report_type,
                FinancialReport.is_deleted == sa.false(),
            )
            .order_by(FinancialReport.row_code)
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="报表数据不存在")

    policy = await resolve_export_policy(db, project_id)
    unit_label = EXPORT_UNIT_LABELS.get(str(policy.unit), str(policy.unit))
    divisor = policy.divisor

    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - 环境缺依赖
        raise HTTPException(status_code=500, detail="openpyxl 未安装，无法导出 Excel") from exc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report_type.value

    # 单位标注行（数值与标注同源；放表头之前，用户一眼看到口径）
    ws.append([f"金额单位：{unit_label}"])
    ws.append([])
    ws.append(["行次代码", "项目", "期末余额", "年初余额", "说明"])

    formulas, definition_hashes = await load_effective_formula_state(
        db, project_id, report_type=report_type,
    )
    for row in rows:
        ws.append(
            [
                row.row_code,
                row.row_name or "",
                convert_amount_for_export(row.current_period_amount, divisor),
                convert_amount_for_export(row.prior_period_amount, divisor),
                status_note(
                    row_status(
                        row,
                        formula_for(formulas, row),
                        definition_hash_for(definition_hashes, row),
                    )
                ),
            ]
        )

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"{report_type.value}_{year}.xlsx"
    ascii_name = filename.encode("ascii", "ignore").decode() or "report.xlsx"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": disposition,
            # 单位口径也进响应头，便于下游 / 审计核对（不必解析 xlsx）
            "X-GT-Export-Unit": str(policy.unit),
            "X-GT-Export-Divisor": str(divisor),
        },
    )


__all__ = [
    "EXPORT_UNIT_LABELS",
    "build_report_excel_response",
    "convert_amount_for_export",
]
