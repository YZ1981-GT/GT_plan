"""M2 实收资本（股本）— 导入导出三级端点 + 外币折算 + 验资核对 + 出资人汇总

6个端点：
- GET  /api/m2-paid-in-capital/{wp_id}/export-template    多sheet空白模板xlsx
- GET  /api/m2-paid-in-capital/{wp_id}/export-data         当前数据xlsx
- POST /api/m2-paid-in-capital/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m2-paid-in-capital/{wp_id}/fx-calculate        批量外币折算（原币×汇率）
- POST /api/m2-paid-in-capital/{wp_id}/verify-calculate    批量验资核对（实缴-验资）
- GET  /api/m2-paid-in-capital/{wp_id}/investor-summary    按出资人汇总

科目编码: 4001实收资本/股本（贷方/权益类！）
公式方向: 期末=期初+贷方-借方（增资在贷方，减资在借方）
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

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.m2_paid_in_capital_service import (
    calc_fx_batch,
    calc_verify_batch,
    export_data,
    export_template,
    import_data,
    summarize_by_investor,
    validate_equity_formulas,
)

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m2-paid-in-capital",
    tags=["M2 实收资本"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m2"

#: 本前缀的 X-3 sheet 码 —— 从 `X3_SHEET_SPECS`（Key_Ledger 单一真源）按短前缀**反查**。
#: 🔴 本模块内不写 X-3 字面量：写死一份即成后端第二真源，前端改键时不会打红。
#: 反查为空 ⇒ 下面 `attach_shape_a_routes` 立即抛 `X3ContractError`（fail-loud，不静默少端点）。
_X3_CODES: frozenset[str] = frozenset(
    code for code, spec in X3_SHEET_SPECS.items() if spec.api_prefix == _IE_API_PREFIX
)

#: 本前缀 sheet 白名单的**唯一真源**（R4.4）。
#:
#: 🔴 本前缀的既有长前缀三态端点**没有** sheet 白名单校验（`sheet: str | None = None` 直接
#:    透传 service），故本任务之前本模块不存在可派生的白名单常量。本任务**不**给既有端点补
#:    校验：那会把「未知 sheet 静默按 service 默认处理」改成 400，属既有行为变更、超出任务
#:    5.1 半径。该存量缺陷已登记 `Deviation_Registry` G6（10 条 = m1 + m2~m10），收口另立
#:    任务。⇒ `IE_SHEETS` 此刻只覆盖 X-3（= 形态 A 端点的白名单）。
IE_SHEETS: frozenset[str] = _X3_CODES

attach_shape_a_routes(router, api_prefix=_IE_API_PREFIX, sheets=_X3_CODES)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class ValidateFormulasRequest(BaseModel):
    """权益类公式方向验证请求"""
    begin: float = Field(..., description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（增资）")
    debit: float = Field(0.0, description="借方发生额（减资）")
    reportedEnd: float | None = Field(None, description="报告期末余额（可选，用于差异校验）")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m2_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（3个sheet：M2-2上市明细/M2-2非上市明细/M2-4外币投资）

    Query params:
        sheet: 可选，指定导出单个sheet（M2-2-listed/M2-2-unlisted/M2-4）

    Requirements: 7.7
    """
    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M2实收资本_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m2_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（3个sheet：M2-2上市明细/M2-2非上市明细/M2-4外币投资）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 7.7
    """
    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M2实收资本_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m2_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持3个sheet：M2-2上市/M2-2非上市/M2-4）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.7
    """
    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 外币折算批量计算（M2-4）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/fx-calculate")
async def m2_fx_calculate(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """批量计算外币折算（M2-4外币投资汇率测算表）

    从 checklist_responses 取 M2-4 数据，逐行计算：
    - 折算本位币 = 原币出资 × 出资日汇率
    - 折算差异 = 折算本位币 - 账面本位币

    Returns:
        {
            items: list[{investor, currency, original_amount, rate, converted, booked, fx_diff}],
            total_fx_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M2-4), 4.2
    """
    result = await calc_fx_batch(db, wp_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 验资核对批量计算（M2-5）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/verify-calculate")
async def m2_verify_calculate(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """批量计算验资核对（M2-5检查表）

    从 checklist_responses 取 M2-5 数据，逐行计算：
    - 验资差异 = 实缴出资 - 验资金额
    - 出资到位率 = 实缴出资 / 认缴出资

    Returns:
        {
            items: list[{investor, subscribed, paid, verified, verify_diff, paid_in_rate}],
            total_paid: float,
            total_verified: float,
            total_diff: float,
            has_material_diff: bool
        }

    Requirements: 7.7 (M2-5), 5.2
    """
    result = await calc_verify_batch(db, wp_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 出资人汇总
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/investor-summary")
async def m2_investor_summary(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按出资人汇总实收资本数据

    从 checklist_responses 按出资人聚合认缴/实缴/验资数据，
    计算出资到位率和验资差异。

    Returns:
        {
            investors: list[{name, subscribed, paid, verified, paid_in_rate, verify_diff}],
            total_subscribed: float,
            total_paid: float,
            total_verified: float,
            overall_paid_in_rate: float,
        }

    Requirements: 5.2
    """
    result = await summarize_by_investor(wp_id, db)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 公式验证（权益类：期末=期初+贷方-借方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m2_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """校验权益类公式方向（期末=期初+贷方-借方）

    实收资本为贷方/权益类科目：
    - 增资（含验资确认）在贷方增加
    - 减资（减少注册资本）在借方减少
    - 期末余额 = 期初 + 贷方发生额 - 借方发生额

    Requirements: 7.7
    """
    result = validate_equity_formulas(
        begin=request.begin,
        credit=request.credit,
        debit=request.debit,
        reported_end=request.reportedEnd,
    )
    return result
