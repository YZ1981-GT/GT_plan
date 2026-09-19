"""M3 库存股 — 导入导出三级端点 + 外币折算/回购注销API + TB取数

5个端点：
- GET  /api/m3-treasury-stock/{wp_id}/export-template    多sheet空白模板xlsx
- GET  /api/m3-treasury-stock/{wp_id}/export-data         当前数据xlsx
- POST /api/m3-treasury-stock/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m3-treasury-stock/{wp_id}/validate-formulas   权益备抵类公式方向验证
- GET  /api/m3-treasury-stock/{wp_id}/tb-seed             TB取数（科目4002）

科目编码: 4002库存股（**借方/权益备抵类！**）
公式方向: 期末=期初+借方-贷方（回购在借方增加，注销在贷方减少，与其他M权益类方向相反！）
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
from app.routers.wp_render_strategies._m3_treasury_stock import (
    validate_contra_equity_formula,
)

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m3-treasury-stock",
    tags=["M3 库存股"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m3"

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


class ContraEquityRow(BaseModel):
    """权益备抵类单行数据"""
    row_key: str = Field("", description="行标识")
    begin: float = Field(0.0, description="期初余额")
    debit: float = Field(0.0, description="借方发生额（回购增加）")
    credit: float = Field(0.0, description="贷方发生额（注销/再售减少）")
    end: float = Field(0.0, description="期末余额（应等于 begin+debit-credit）")


class ValidateFormulasRequest(BaseModel):
    """权益备抵类公式验证请求（批量行）"""
    rows: list[ContraEquityRow] = Field(..., description="待校验行列表")


class ValidateFormulasResponse(BaseModel):
    """公式验证响应"""
    errors: list[dict[str, Any]] = Field(default_factory=list)
    is_valid: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m3_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（3个sheet：M3-2明细/M3-4外币/M3-5检查表）

    Query params:
        sheet: 可选，指定导出单个sheet（M3-2/M3-4/M3-5）

    Requirements: 7.7
    """
    from app.services.m3_treasury_stock_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M3库存股_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m3_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（3个sheet：M3-2明细/M3-4外币/M3-5检查表）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 7.7
    """
    from app.services.m3_treasury_stock_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M3库存股_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m3_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持3个sheet：M3-2/M3-4/M3-5）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.7
    """
    from app.services.m3_treasury_stock_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 权益备抵类公式验证（期末=期初+借方-贷方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m3_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> ValidateFormulasResponse:
    """校验权益备抵类公式方向（期末=期初+借方-贷方）

    库存股（4002）为借方/权益备抵科目：
    - 回购股份（借记库存股）在借方增加
    - 注销/再售（贷记库存股）在贷方减少
    - 期末 = 期初 + 借方 - 贷方（与M2/M4/M5/M6方向相反！）

    Body: { rows: [{row_key, begin, debit, credit, end}] }
    Returns: { errors: [...], is_valid: bool }

    Requirements: 7.7
    """
    # 转换为 renderer 函数期望的 dict 列表
    rows_dicts = [row.model_dump() for row in request.rows]
    errors = validate_contra_equity_formula(rows_dicts)
    return ValidateFormulasResponse(
        errors=errors,
        is_valid=len(errors) == 0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TB 取数（科目4002库存股）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/tb-seed")
async def m3_tb_seed(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取TB科目4002库存股的种子数据

    从 tb_balance 查询科目4002（库存股），返回借方/贷方发生额和当前净额。
    库存股为权益备抵借方科目：current_amount = debit - credit（借方净额）

    Returns:
        {
            account_code: "4002",
            debit_amount: float,   # 本期借方发生额（回购增加）
            credit_amount: float,  # 本期贷方发生额（注销减少）
            current_amount: float, # 借方净额
            direction: "debit"
        }

    Requirements: 7.7
    """
    from app.services.m3_treasury_stock_service import get_tb_seed

    result = await get_tb_seed(wp_id, db)
    return result
