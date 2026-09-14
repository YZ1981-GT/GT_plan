"""M4 资本公积 — 导入导出三级端点 + 资本公积变动API + 公式校验 + J3联动

6个端点：
- GET  /api/m4-capital-reserve/{wp_id}/export-template     多sheet空白模板xlsx
- GET  /api/m4-capital-reserve/{wp_id}/export-data          当前数据xlsx
- POST /api/m4-capital-reserve/{wp_id}/import-data          解析xlsx写入（multipart）
- GET  /api/m4-capital-reserve/{wp_id}/reserve-changes      资本公积变动明细（M4-2）
- PUT  /api/m4-capital-reserve/{wp_id}/validate-formulas    权益类公式方向验证
- GET  /api/m4-capital-reserve/{wp_id}/j3-linkage           J3股份支付权益结算联动

科目编码: 4002资本公积（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（资本溢价+其他资本公积在贷方增加，转出在借方减少）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 6.5
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
from app.routers.wp_render_strategies._m4_capital_reserve import (
    validate_equity_formula,
)

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m4-capital-reserve",
    tags=["M4 资本公积"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m4"

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


class EquityRow(BaseModel):
    """权益类贷方单行数据"""
    row_key: str = Field("", description="行标识")
    begin: float = Field(0.0, description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（增加：溢价/股份支付等）")
    debit: float = Field(0.0, description="借方发生额（减少：转增资本等）")
    end_balance: float = Field(0.0, description="期末余额（应等于 begin+credit-debit）")


class ValidateFormulasRequest(BaseModel):
    """权益类贷方公式验证请求（批量行）"""
    rows: list[EquityRow] = Field(..., description="待校验行列表")


class ValidateFormulasResponse(BaseModel):
    """公式验证响应"""
    errors: list[dict[str, Any]] = Field(default_factory=list)
    is_valid: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m4_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（2个sheet：M4-2明细表/M4-4检查表）

    Query params:
        sheet: 可选，指定导出单个sheet（M4-2/M4-4）

    Requirements: 6.5
    """
    from app.services.m4_capital_reserve_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M4资本公积_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m4_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（2个sheet：M4-2明细表/M4-4检查表）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 6.5
    """
    from app.services.m4_capital_reserve_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M4资本公积_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m4_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持2个sheet：M4-2明细/M4-4检查表）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.5
    """
    from app.services.m4_capital_reserve_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 资本公积变动明细（reserve-changes）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/reserve-changes")
async def m4_reserve_changes(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取资本公积变动明细（M4-2数据汇总）

    返回资本溢价+其他资本公积的本期变动：
    - premium_changes: 资本溢价明细变动列表
    - other_changes: 其他资本公积明细变动列表
    - summary: 汇总（期初/增加/减少/期末）

    资本公积为权益类贷方科目：期末=期初+贷方-借方

    Returns:
        {
            premium_changes: list[{source, begin, increase, decrease, end, reason}],
            other_changes: list[{source, begin, increase, decrease, end, reason}],
            summary: { premium_total, other_total, grand_total },
            account_code: "4002"
        }

    Requirements: 6.5
    """
    from app.services.m4_capital_reserve_service import get_reserve_changes

    result = await get_reserve_changes(wp_id, db)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 权益类贷方公式验证（期末=期初+贷方-借方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.put("/{wp_id}/validate-formulas")
async def m4_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> ValidateFormulasResponse:
    """校验权益类贷方公式方向（期末=期初+贷方-借方）

    资本公积（4002）为贷方/权益类科目：
    - 资本溢价（出资超面值）在贷方增加
    - 其他资本公积（股份支付权益结算等）在贷方增加
    - 转出（资本公积转增资本）在借方减少
    - 期末 = 期初 + 贷方 - 借方（标准权益类方向）

    Body: { rows: [{row_key, begin, credit, debit, end_balance}] }
    Returns: { errors: [...], is_valid: bool }

    Requirements: 6.5
    """
    rows_dicts = [row.model_dump() for row in request.rows]
    errors = validate_equity_formula(rows_dicts)
    return ValidateFormulasResponse(
        errors=errors,
        is_valid=len(errors) == 0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# J3 股份支付权益结算联动
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/j3-linkage")
async def m4_j3_linkage(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """获取J3股份支付权益结算联动数据

    从J3底稿数据中提取等待期内确认的股份支付金额（计入其他资本公积），
    返回核对结果：J3确认金额 vs M4账面其他资本公积增加额。

    Returns:
        {
            j3_equity_settled: float,     # J3等待期确认金额
            m4_other_increase: float,     # M4其他资本公积本期增加
            diff: float,                  # 差异
            is_consistent: bool,          # 差异是否在容差内
            m2_fx_diff: float,            # M2外币出资折算差异
            cross_refs: list[str]         # 关联底稿引用
        }

    Requirements: 6.5
    """
    from app.services.m4_capital_reserve_service import get_j3_linkage

    result = await get_j3_linkage(wp_id, db)
    return result
