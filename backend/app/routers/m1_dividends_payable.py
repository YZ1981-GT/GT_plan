"""M1 应付股利（利润）— 导入导出三级端点 + 外币折算 + 股利测算 + 公式验证

6个端点：
- POST /api/m1-dividends-payable/{wp_id}/export-template    多sheet空白模板xlsx
- POST /api/m1-dividends-payable/{wp_id}/export-data         当前数据xlsx
- POST /api/m1-dividends-payable/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m1-dividends-payable/{wp_id}/validate-formulas   校验负债类公式方向（期末=期初+贷-借）
- GET  /api/m1-dividends-payable/{wp_id}/fx-calculation      外币折算结果（M1-4）
- GET  /api/m1-dividends-payable/{wp_id}/dividend-calculation 股利测算结果（M1-5）

科目编码: 2232应付股利（贷方/负债类）
公式方向: 期末=期初+贷方-借方（宣告在贷方增加，实际支付在借方减少）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 7.7
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.m1_dividends_payable_service import (
    calc_fx_conversion,
    calc_dividend_estimation,
    export_data,
    export_template,
    import_data,
    validate_liability_formulas,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m1-dividends-payable",
    tags=["M1 应付股利"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class ValidateFormulasRequest(BaseModel):
    """负债类公式方向验证请求"""
    begin: float = Field(..., description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（宣告分配）")
    debit: float = Field(0.0, description="借方发生额（实际支付）")
    reportedEnd: float | None = Field(None, description="报告期末余额（可选，用于差异校验）")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助：从 wp_id 获取 project_id 和 year
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_wp_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 取关联的 project_id 和 audit_year."""
    result = await db.execute(
        sa.text("""
            SELECT wp.project_id, p.audit_year
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
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/export-template")
async def m1_export_template(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算）

    Requirements: 7.7
    """
    buffer = await export_template(wp_id, db)
    filename = "M1应付股利_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/export-data")
async def m1_export_data(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（3个sheet：M1-2明细表 / M1-4外币汇率 / M1-5股利测算）

    Requirements: 7.7
    """
    buffer = await export_data(wp_id, db)
    filename = "M1应付股利_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m1_import_data(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持3个sheet：M1-2/M1-4/M1-5）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.7
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 公式验证（负债类：期末=期初+贷方-借方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m1_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """校验负债类公式方向（期末=期初+贷方-借方）

    应付股利为贷方/负债类科目：
    - 宣告分配时贷方增加
    - 实际支付时借方减少
    - 期末余额 = 期初 + 贷方发生额 - 借方发生额

    Requirements: 7.7
    """
    result = validate_liability_formulas(
        begin=request.begin,
        credit=request.credit,
        debit=request.debit,
        reported_end=request.reportedEnd,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 外币折算（M1-4）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/fx-calculation")
async def m1_fx_calculation(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """外币折算计算结果（M1-4外币汇率测算表）

    对外币股东的应付股利按期末即期汇率折算本位币，
    计算汇兑差异 = 折算本位币 - 账面本位币。

    Returns:
        {
            items: list[{shareholder, currency, original_amount, rate, converted, booked, fx_diff}],
            total_fx_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M1-4)
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]

    result = await calc_fx_conversion(db, project_id, wp_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 股利测算（M1-5）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/dividend-calculation")
async def m1_dividend_calculation(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """股利测算计算结果（M1-5应付股利测算表）

    接收M6利润分配的可供分配利润，按分配比例测算应宣告股利，
    与账面宣告比较差异。

    Returns:
        {
            items: list[{shareholder, distributable_profit, ratio, estimated_dividend, booked_dividend, diff}],
            total_estimated: float,
            total_booked: float,
            total_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M1-5)
    """
    ctx = await _get_wp_context(wp_id, db)
    project_id = ctx["project_id"]

    result = await calc_dividend_estimation(db, project_id, wp_id)
    return result
