"""L5 长期应付款 — 导入导出三级端点 + 摊销表生成 + 公式验证

5个端点：
- GET  /api/workpapers/{wp_id}/l5/export-template   多sheet空白模板xlsx
- GET  /api/workpapers/{wp_id}/l5/export-data        当前数据xlsx
- POST /api/workpapers/{wp_id}/l5/import-data        解析xlsx写入（multipart）
- POST /api/workpapers/{wp_id}/l5/generate-amortization  生成未确认融资费用摊销表
- POST /api/workpapers/{wp_id}/l5/validate-formulas  校验公式方向（负债类+备抵类）

科目编码: 2701长期应付款（贷方/负债类） + 未确认融资费用（借方/备抵）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 4.1, 8.2
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.l5_long_term_payables_service import (
    calc_net_payable,
    export_data,
    export_template,
    generate_amortization_schedule,
    import_data,
    related_party_check_summary,
    validate_liability_direction,
    validate_schedule,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/l5", tags=["L5 长期应付款"])


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateAmortizationRequest(BaseModel):
    """未确认融资费用摊销表生成请求"""
    initialCost: float = Field(..., description="期初未确认融资费用（初始摊余成本）")
    repayments: list[float] = Field(default_factory=list, description="各期还款额")
    eir: float = Field(..., ge=0, description="实际利率")
    periods: int = Field(..., ge=1, le=100, description="期数")


class ValidateFormulasRequest(BaseModel):
    """公式方向验证请求（支持负债类+备抵类）"""
    begin: float = Field(..., description="期初余额")
    credit: float = Field(0.0, description="贷方发生额")
    debit: float = Field(0.0, description="借方发生额")
    reportedEnd: float | None = Field(None, description="报告期末余额（可选，用于差异校验）")
    direction: str = Field(
        "liability",
        description="科目方向: liability=负债类贷方(期末=期初+贷-借), contra=备抵类借方(期末=期初+借-贷)",
    )


class NetPayableRequest(BaseModel):
    """净额计算请求"""
    payableAmount: float = Field(..., description="长期应付款审定数")
    unrecognizedAmount: float = Field(..., description="未确认融资费用审定数")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/export-template")
async def l5_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多sheet，按动态行表格分sheet）

    Query params:
        sheet: 可选，指定导出单个sheet（L5-2/L5-3/L5-5/L5-6/L5-7）

    Requirements: 8.2
    """
    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"L5长期应付款_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/export-data")
async def l5_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多sheet）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 8.2
    """
    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"L5长期应付款_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/import-data")
async def l5_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持多sheet）

    Query params:
        sheet: 可选，指定导入目标sheet

    Requirements: 8.2
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


@router.post("/generate-amortization")
async def l5_generate_amortization(
    wp_id: str,
    request: GenerateAmortizationRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """生成未确认融资费用摊销表（实际利率法）

    每期摊销 = 期初摊余成本 × 实际利率
    最后一期尾差调整使余额趋零。

    Requirements: 4.1
    """
    schedule = generate_amortization_schedule(
        initial_cost=request.initialCost,
        repayments=request.repayments,
        eir=request.eir,
        periods=request.periods,
    )

    validation = validate_schedule(schedule)

    total_amortization = sum(row["amortization"] for row in schedule)

    return {
        "schedule": schedule,
        "validation": validation,
        "summary": {
            "totalAmortization": round(total_amortization, 2),
            "periods": request.periods,
            "eir": request.eir,
            "initialCost": request.initialCost,
        },
    }


@router.post("/validate-formulas")
async def l5_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """校验公式方向

    负债类贷方：期末 = 期初 + 贷方 − 借方
    备抵类借方：期末 = 期初 + 借方 − 贷方

    Requirements: 2.4
    """
    result = validate_liability_direction(
        begin=request.begin,
        credit=request.credit,
        debit=request.debit,
        reported_end=request.reportedEnd,
        direction=request.direction,
    )
    return result
