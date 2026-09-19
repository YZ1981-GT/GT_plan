"""M10 其他权益工具 — 导入导出三级端点 + 负债权益区分API + 公式校验

5个端点：
- GET  /api/m10-other-equity-instruments/{wp_id}/export-template       空白模板xlsx
- GET  /api/m10-other-equity-instruments/{wp_id}/export-data            当前数据xlsx
- POST /api/m10-other-equity-instruments/{wp_id}/import-data            解析xlsx写入（multipart）
- POST /api/m10-other-equity-instruments/{wp_id}/validate-formulas      权益类公式校验（期末=期初+贷方-借方）
- GET  /api/m10-other-equity-instruments/{wp_id}/classification-summary CAS37负债权益区分汇总

科目编码: 4003其他权益工具（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（发行在贷方增加，赎回/转换在借方减少）
CAS37核心: 永续债/优先股按合同义务判定分类为权益工具或金融负债
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 6.6
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

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m10-other-equity-instruments",
    tags=["M10 其他权益工具"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m10"

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


class FormulaRow(BaseModel):
    """权益类公式校验行"""
    row_key: str = Field("", description="行标识")
    period_begin: float = Field(0.0, description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（发行）")
    debit: float = Field(0.0, description="借方发生额（赎回/转换）")
    period_end: float = Field(0.0, description="期末余额")


class ValidateFormulasRequest(BaseModel):
    """公式校验请求"""
    rows: list[FormulaRow] = Field(default_factory=list, description="待校验行列表")


class FormulaError(BaseModel):
    """公式校验错误"""
    row_key: str = Field(description="行标识")
    begin: float = Field(description="期初")
    credit: float = Field(description="贷方")
    debit: float = Field(description="借方")
    actual_end: float = Field(description="实际期末")
    expected_end: float = Field(description="期望期末=期初+贷方-借方")
    diff: float = Field(description="差异")


class ValidateFormulasResponse(BaseModel):
    """公式校验响应"""
    total_rows: int = Field(description="总校验行数")
    error_count: int = Field(description="错误行数")
    errors: list[FormulaError] = Field(default_factory=list, description="错误明细")
    is_valid: bool = Field(description="全部通过=True")


class ClassificationItem(BaseModel):
    """单项金融工具分类"""
    instrument_name: str = Field("", description="工具名称")
    classification: str = Field("", description="分类结论: equity/liability")
    amount: float = Field(0.0, description="金额")


class ClassificationSummaryResponse(BaseModel):
    """CAS37负债权益区分汇总"""
    equity_total: float = Field(0.0, description="归入权益金额合计")
    liability_total: float = Field(0.0, description="归入负债金额合计")
    total: float = Field(0.0, description="工具总额")
    is_consistent: bool = Field(True, description="金额守恒=equity+liability==total")
    items: list[ClassificationItem] = Field(default_factory=list, description="逐项明细")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m10_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（M10-2明细表 永续债/优先股）

    Query params:
        sheet: 可选，指定导出sheet（M10-2）

    Requirements: 6.6
    """
    from app.services.m10_other_equity_instruments_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M10其他权益工具_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m10_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（M10-2明细表 当前永续债/优先股数据）

    Query params:
        sheet: 可选，指定导出sheet

    Requirements: 6.6
    """
    from app.services.m10_other_equity_instruments_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M10其他权益工具_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m10_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（M10-2明细表动态行 永续债/优先股）

    Query params:
        sheet: 可选，指定导入目标sheet（M10-2）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.6
    """
    from app.services.m10_other_equity_instruments_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 权益类公式校验
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m10_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    current_user: User = Depends(get_current_user),
) -> ValidateFormulasResponse:
    """校验权益类公式：期末=期初+贷方-借方

    调用渲染策略的 validate_equity_formula 纯函数，逐行验证
    权益类贷方科目公式（发行在贷方增加，赎回/转换在借方减少）。

    Body: { rows: [{ row_key, period_begin, credit, debit, period_end }] }
    Returns: { total_rows, error_count, errors, is_valid }

    Requirements: 6.4, 2.4
    """
    from app.routers.wp_render_strategies._m10_other_equity_instruments import (
        validate_equity_formula,
    )

    # 转换为 validate_equity_formula 所需格式
    raw_rows = [
        {
            "row_key": r.row_key,
            "begin": r.period_begin,
            "credit": r.credit,
            "debit": r.debit,
            "end_balance": r.period_end,
        }
        for r in request.rows
    ]

    errors = validate_equity_formula(raw_rows)

    return ValidateFormulasResponse(
        total_rows=len(request.rows),
        error_count=len(errors),
        errors=[FormulaError(**e) for e in errors],
        is_valid=len(errors) == 0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CAS37 负债权益区分汇总
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/classification-summary")
async def m10_classification_summary(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ClassificationSummaryResponse:
    """获取CAS37负债权益区分汇总

    从 checklist_responses 中查询 M10-4 负债权益区分检查项，
    聚合归入权益/负债的金额，校验金额守恒（equity+liability==total）。

    Returns:
        { equity_total, liability_total, total, is_consistent, items }

    Requirements: 4.2-4.3, 6.1-6.3
    """
    from app.services.m10_other_equity_instruments_service import (
        get_classification_summary,
    )

    return await get_classification_summary(wp_id, db)
