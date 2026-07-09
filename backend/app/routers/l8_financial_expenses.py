"""L8 财务费用 — 导入导出三级端点 + 利息测算汇总 + 截止提取

端点：
- GET  /api/l8-financial-expenses/{wp_id}/export-template   多sheet空白模板xlsx
- GET  /api/l8-financial-expenses/{wp_id}/export-data        当前数据xlsx
- POST /api/l8-financial-expenses/{wp_id}/import-data        解析xlsx写入（multipart）
- GET  /api/l8-financial-expenses/{wp_id}/interest-summary   利息测算汇总(L1/L3/L4/L5)
- GET  /api/l8-financial-expenses/{wp_id}/cutoff-extract     截止自动提取(序时账±N天)

科目编码: 6603财务费用（**损益类/借方**）— 本期发生额=借方发生-贷方发生
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 4.5, 6.1, 8.8
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.l8_financial_expenses_service import (
    aggregate_interest_from_l_cycle,
    export_data,
    export_template,
    extract_cutoff_entries,
    import_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/l8-financial-expenses",
    tags=["L8 财务费用"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助：从 wp_id 获取 project_id 和 year
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_wp_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 取关联的 project_id 和 audit_year."""
    result = await db.execute(
        sa.text("""
            SELECT wp.project_id, p.audit_year,
                   COALESCE(p.audit_period_end, MAKE_DATE(p.audit_year, 12, 31)) AS report_date
            FROM working_papers wp
            JOIN projects p ON p.id = wp.project_id
            WHERE wp.id = :wp_id
        """),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")
    return {
        "project_id": row.project_id,
        "year": int(row.audit_year or 2025),
        "report_date": row.report_date,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def l8_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多sheet，按动态行表格分sheet）

    Query params:
        sheet: 可选，指定导出单个sheet（L8-1/L8-2/L8-3/L8-4/L8-5）

    Requirements: 8.8
    """
    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"L8财务费用_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def l8_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多sheet）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 8.8
    """
    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"L8财务费用_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def l8_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持多sheet）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 8.8
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 利息测算汇总（L1/L3/L4/L5联动）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/interest-summary")
async def l8_interest_summary(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """利息测算汇总 — 从L1/L3/L4/L5底稿取利息值

    汇总L筹资循环各底稿利息测算结果：
    - L1 短期借款利息
    - L3 长期借款利息
    - L4 应付债券利息费用
    - L5 未确认融资费用摊销

    Requirements: 4.5
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]

    summary = await aggregate_interest_from_l_cycle(db, project_id)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# 截止自动提取
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/cutoff-extract")
async def l8_cutoff_extract(
    wp_id: str,
    days: int = Query(default=5, ge=1, le=30, description="报告日±天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """截止自动提取 — 序时账±N天

    从tb_ledger提取报告日前后±N天的6603财务费用序时账明细，
    自动判定跨期费用。

    Returns:
        { entries: list, total_count: int, cross_period_count: int, report_date: str }

    Requirements: 6.1
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]
    report_date = ctx["report_date"]

    # report_date 可能是 date 或 datetime
    if hasattr(report_date, "date"):
        report_date = report_date.date()
    elif not isinstance(report_date, date):
        report_date = date(ctx["year"], 12, 31)

    entries = await extract_cutoff_entries(
        db, project_id, report_date, days=days, account_code="6603"
    )

    cross_period_count = sum(1 for e in entries if e.get("is_cross_period"))

    return {
        "entries": entries,
        "total_count": len(entries),
        "cross_period_count": cross_period_count,
        "report_date": report_date.isoformat(),
        "days_window": days,
    }
