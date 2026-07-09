"""L4 应付债券 — 导入导出三级端点 + 后续计量生成 + IRR求解 + 公式验证

6个端点：
- POST /api/workpapers/{wp_id}/l4/export-template          多sheet空白模板xlsx（89列区段分sheet）
- POST /api/workpapers/{wp_id}/l4/export-data               当前数据xlsx
- POST /api/workpapers/{wp_id}/l4/import-data               解析xlsx写入（multipart）
- POST /api/workpapers/{wp_id}/l4/generate-schedule         生成EIR后续计量表（2分支）
- POST /api/workpapers/{wp_id}/l4/solve-eir                 求解实际利率（IRR二分法）
- POST /api/workpapers/{wp_id}/l4/validate-formulas         校验公式方向（负债类贷方）

科目编码: 2502应付债券（贷方/负债类）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 4.1, 6.4, 12.2
"""

from __future__ import annotations

import logging
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.l4_bonds_payable_service import (
    calc_equity_component,
    calc_initial_amount,
    calc_liability_component,
    calc_premium_discount,
    export_data,
    export_template,
    generate_eir_schedule,
    import_data,
    solve_eir,
    validate_liability_direction,
    validate_schedule,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/l4", tags=["L4 应付债券"])


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class GenerateScheduleRequest(BaseModel):
    """EIR后续计量表生成请求"""
    initialCost: float = Field(..., description="初始入账金额（期初摊余成本）")
    faceValue: float = Field(..., description="面值")
    couponRate: float = Field(..., ge=0, description="票面利率")
    eir: float = Field(..., gt=0, description="实际利率")
    periods: int = Field(..., ge=1, le=100, description="期数")
    branch: Literal["bullet", "installment"] = Field(
        "installment", description="分支: bullet=到期一次还本付息, installment=分期付息到期一次还本"
    )


class SolveEIRRequest(BaseModel):
    """IRR求解请求"""
    cashFlows: list[float] = Field(..., min_length=1, description="未来各期现金流（正数）")
    initialAmount: float = Field(..., gt=0, description="初始入账金额")


class ValidateFormulasRequest(BaseModel):
    """公式方向验证请求"""
    begin: float = Field(..., description="期初余额")
    credit: float = Field(0.0, description="贷方发生额")
    debit: float = Field(0.0, description="借方发生额")
    reportedEnd: float | None = Field(None, description="报告期末余额（可选，用于差异校验）")


class EquityLiabRequest(BaseModel):
    """权益负债划分请求"""
    cashFlows: list[float] = Field(..., min_length=1, description="未来各期现金流")
    marketRate: float = Field(..., gt=0, description="市场利率")
    totalProceeds: float = Field(..., gt=0, description="发行总额")


class InitialMeasureRequest(BaseModel):
    """初始计量请求"""
    issuePrice: float = Field(..., description="发行价格")
    transactionCost: float = Field(..., ge=0, description="交易费用")
    faceValue: float = Field(..., gt=0, description="面值")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/export-template")
async def l4_export_template(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多sheet，L4-2区段89列分sheet）

    Requirements: 12.2
    """
    buffer = await export_template(wp_id, db)
    filename = "L4应付债券_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/export-data")
async def l4_export_data(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多sheet）

    Requirements: 12.2
    """
    buffer = await export_data(wp_id, db)
    filename = "L4应付债券_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/import-data")
async def l4_import_data(
    wp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持多sheet区段合并）

    Requirements: 12.2
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


@router.post("/generate-schedule")
async def l4_generate_schedule(
    wp_id: str,
    request: GenerateScheduleRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """生成EIR后续计量表（2分支）

    根据初始摊余成本、面值、票面利率、实际利率、期数和分支类型，
    生成完整的摊销表。

    Requirements: 4.1, 9.4
    """
    schedule = generate_eir_schedule(
        initial_cost=request.initialCost,
        face_value=request.faceValue,
        coupon_rate=request.couponRate,
        eir=request.eir,
        periods=request.periods,
        branch=request.branch,
    )

    validation = validate_schedule(schedule, request.faceValue)

    # 汇总
    total_interest_expense = sum(row["interestExpense"] for row in schedule)
    total_coupon = sum(row["couponInterest"] for row in schedule)
    total_amortization = sum(row["amortization"] for row in schedule)

    return {
        "schedule": schedule,
        "validation": validation,
        "summary": {
            "totalInterestExpense": round(total_interest_expense, 2),
            "totalCouponInterest": round(total_coupon, 2),
            "totalAmortization": round(total_amortization, 2),
            "periods": request.periods,
            "branch": request.branch,
        },
    }


@router.post("/solve-eir")
async def l4_solve_eir(
    wp_id: str,
    request: SolveEIRRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """求解实际利率（IRR二分法）

    使未来现金流现值=初始入账金额的折现率。

    Requirements: 6.4
    """
    eir = solve_eir(request.cashFlows, request.initialAmount)

    if eir <= 0.0001:
        return {
            "eir": 0.0,
            "converged": False,
            "message": "IRR不收敛，请检查现金流或手动输入实际利率",
        }

    return {
        "eir": eir,
        "eirPercent": round(eir * 100, 4),
        "converged": True,
    }


@router.post("/validate-formulas")
async def l4_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """校验公式方向（负债类贷方：期末=期初+贷方-借方）

    Requirements: 2.4
    """
    result = validate_liability_direction(
        begin=request.begin,
        credit=request.credit,
        debit=request.debit,
        reported_end=request.reportedEnd,
    )
    return result
