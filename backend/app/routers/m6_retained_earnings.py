"""M6 未分配利润 — 导入导出三级端点 + 利润分配结转API + 公式校验

5个端点：
- GET  /api/m6-retained-earnings/{wp_id}/export-template       多sheet空白模板xlsx
- GET  /api/m6-retained-earnings/{wp_id}/export-data           当前数据xlsx
- POST /api/m6-retained-earnings/{wp_id}/import-data           解析xlsx写入（multipart）
- POST /api/m6-retained-earnings/{wp_id}/validate-formulas     校验权益类公式方向（期末=期初+贷方-借方）
- GET  /api/m6-retained-earnings/{wp_id}/distribution-summary  利润分配结转汇总（M5/M1联动）

科目编码: 4104利润分配-未分配利润（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（净利润转入贷方增加，分配时借方减少）
核心公式链: 期末未分配利润=期初+本年净利润-提取盈余公积-分配股利
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

import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from app.routers.wp_render_strategies._x3_adjustment_import_export import (
    X3_SHEET_SPECS,
    attach_shape_a_routes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m6-retained-earnings",
    tags=["M6 未分配利润"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m6"

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
    """权益类公式方向验证请求（支持批量行）"""
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="待验证行列表，每行含 {begin, credit, debit, reportedEnd?}",
    )


class ValidateFormulasRow(BaseModel):
    """单行校验结果"""
    begin: float = Field(0.0, description="期初余额")
    credit: float = Field(0.0, description="贷方发生额（净利润转入）")
    debit: float = Field(0.0, description="借方发生额（分配）")
    calculated_end: float = Field(0.0, description="计算期末=期初+贷方-借方")
    reported_end: float | None = Field(None, description="报告期末余额")
    diff: float = Field(0.0, description="差异=计算-报告")
    is_valid: bool = Field(True, description="是否通过校验")


class ValidateFormulasResponse(BaseModel):
    """公式方向批量验证结果"""
    total_rows: int = Field(0, description="总行数")
    valid_rows: int = Field(0, description="通过行数")
    invalid_rows: int = Field(0, description="不通过行数")
    results: list[ValidateFormulasRow] = Field(default_factory=list)
    formula_description: str = Field(
        "权益类贷方：期末=期初+贷方-借方",
        description="公式说明",
    )


class DistributionSummaryResponse(BaseModel):
    """利润分配结转汇总（用于M5/M1联动核对）"""
    begin: float = Field(0.0, description="期初未分配利润")
    net_profit: float = Field(0.0, description="本年净利润")
    distributable: float = Field(0.0, description="可供分配利润=期初+本年净利润")
    surplus_accrual: float = Field(0.0, description="提取盈余公积（法定+任意）")
    dividend: float = Field(0.0, description="应付普通股股利")
    retained_end: float = Field(0.0, description="期末未分配利润")
    prior_adjustment: float = Field(0.0, description="前期差错更正/会计政策变更调整")
    formula_check: bool = Field(True, description="公式链是否勾稽")
    formula_diff: float = Field(0.0, description="公式链差异")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助：从 wp_id 获取 project_id 和 year
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_wp_context(wp_id: str, db: AsyncSession) -> dict[str, Any]:
    """从 wp_id 取关联的 project_id 和 audit_year."""
    result = await db.execute(
        sa.text("""
            SELECT wp.project_id, p.audit_year
            FROM working_paper wp
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


@router.get("/{wp_id}/export-template")
async def m6_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（多sheet：M6-2明细表 + M6-1审定表）

    Query params:
        sheet: 可选，指定导出单个sheet（M6-1/M6-2）

    Requirements: 6.6
    """
    from app.services.m6_retained_earnings_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M6未分配利润_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m6_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（多sheet：M6-2明细表 + M6-1审定表）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 6.6
    """
    from app.services.m6_retained_earnings_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M6未分配利润_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m6_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（仅M6-2明细表动态行）

    Query params:
        sheet: 可选，指定导入目标sheet（默认M6-2）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.6
    """
    from app.services.m6_retained_earnings_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 公式验证（权益类：期末=期初+贷方-借方）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/validate-formulas")
async def m6_validate_formulas(
    wp_id: str,
    request: ValidateFormulasRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateFormulasResponse:
    """校验权益类公式方向（期末=期初+贷方-借方）

    未分配利润为贷方/权益类科目（4104）：
    - 本年净利润转入时贷方增加
    - 提取盈余公积/分配股利时借方减少
    - 期末余额 = 期初 + 贷方发生额 - 借方发生额

    Body: { rows: [{begin, credit, debit, reportedEnd?}] }
    Returns: ValidateFormulasResponse

    Requirements: 6.6
    """
    results: list[ValidateFormulasRow] = []
    valid_count = 0

    for row_data in request.rows:
        begin = float(row_data.get("begin", 0) or 0)
        credit = float(row_data.get("credit", 0) or 0)
        debit = float(row_data.get("debit", 0) or 0)
        reported_end = row_data.get("reportedEnd")

        # 权益类贷方：期末=期初+贷方-借方
        calculated_end = begin + credit - debit
        diff = 0.0
        is_valid = True

        if reported_end is not None:
            reported_end = float(reported_end)
            diff = round(calculated_end - reported_end, 2)
            is_valid = abs(diff) < 1.0  # 容差1元

        if is_valid:
            valid_count += 1

        results.append(ValidateFormulasRow(
            begin=begin,
            credit=credit,
            debit=debit,
            calculated_end=round(calculated_end, 2),
            reported_end=reported_end,
            diff=diff,
            is_valid=is_valid,
        ))

    return ValidateFormulasResponse(
        total_rows=len(results),
        valid_rows=valid_count,
        invalid_rows=len(results) - valid_count,
        results=results,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 利润分配结转汇总（M5/M1联动）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/distribution-summary")
async def m6_distribution_summary(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DistributionSummaryResponse:
    """获取利润分配结转汇总（用于M5/M1联动核对）

    从M6-2明细表数据汇总利润分配全过程：
    - 期初未分配利润
    - 本年净利润（从本年利润结转）
    - 可供分配利润 = 期初 + 本年净利润
    - 提取盈余公积（法定+任意，联动M5核对）
    - 应付股利（联动M1核对）
    - 期末未分配利润 = 期初 + 本年净利润 - 提取盈余公积 - 分配股利

    核心公式链：期末=期初+本年净利润-提取盈余公积-分配股利

    Returns: DistributionSummaryResponse

    Requirements: 6.6
    """
    from app.services.m6_retained_earnings_service import get_distribution_summary

    ctx = await _get_wp_context(wp_id, db)
    result = await get_distribution_summary(wp_id, db, ctx["project_id"])
    return DistributionSummaryResponse(**result)
