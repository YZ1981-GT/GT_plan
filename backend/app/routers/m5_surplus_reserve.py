"""M5 盈余公积 — 导入导出三级端点 + 计提测试API + 公式校验

4个端点：
- GET  /api/m5-surplus-reserve/{wp_id}/export-template     多sheet空白模板xlsx
- GET  /api/m5-surplus-reserve/{wp_id}/export-data          当前数据xlsx
- POST /api/m5-surplus-reserve/{wp_id}/import-data          解析xlsx写入（multipart）
- POST /api/m5-surplus-reserve/{wp_id}/accrual-test         法定10%计提验证

科目编码: 4101盈余公积（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（法定盈余公积按净利润10%计提，累计达注册资本50%可停止）
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
    prefix="/api/m5-surplus-reserve",
    tags=["M5 盈余公积"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m5"

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


class AccrualTestRequest(BaseModel):
    """法定盈余公积计提测试请求"""
    net_profit: float | None = Field(None, description="本期净利润（来自M6，可选覆盖）")
    prior_year_loss: float = Field(0.0, description="弥补以前年度亏损金额")
    booked_accrual: float = Field(0.0, description="账面已计提金额")
    accumulated_reserve: float = Field(0.0, description="累计法定盈余公积余额")
    registered_capital: float = Field(0.0, description="注册资本")
    rate: float = Field(0.1, description="法定计提比例（默认10%）")


class AccrualTestResponse(BaseModel):
    """法定盈余公积计提测试结果"""
    net_profit: float = Field(0.0, description="本期净利润")
    prior_year_loss: float = Field(0.0, description="弥补以前年度亏损")
    accrual_base: float = Field(0.0, description="计提基数=净利润-弥补亏损")
    rate: float = Field(0.1, description="法定计提比例")
    estimated_accrual: float = Field(0.0, description="应计提金额=基数×比例")
    booked_accrual: float = Field(0.0, description="账面已计提")
    diff: float = Field(0.0, description="差异=应计提-账面")
    accumulated_reserve: float = Field(0.0, description="累计法定盈余公积")
    registered_capital: float = Field(0.0, description="注册资本")
    ceiling_reached: bool = Field(False, description="是否达到注册资本50%上限")
    ceiling_threshold: float = Field(0.0, description="注册资本50%金额")
    is_compliant: bool = Field(True, description="计提是否合规")
    warnings: list[str] = Field(default_factory=list, description="告警信息")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m5_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（M5-2明细表/M5-4计提检查表）

    Query params:
        sheet: 可选，指定导出单个sheet（M5-2/M5-4）

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M5盈余公积_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m5_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（M5-2明细表/M5-4计提检查表）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M5盈余公积_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m5_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（支持M5-2明细/M5-4计提检查表）

    Query params:
        sheet: 可选，指定导入目标sheet

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 法定10%计提测试
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/accrual-test")
async def m5_accrual_test(
    wp_id: str,
    request: AccrualTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccrualTestResponse:
    """法定盈余公积计提测试（10%计提验证 + 50%上限判断）

    验证逻辑：
    1. 计提基数 = 净利润 - 弥补以前年度亏损
    2. 应计提 = 计提基数 × 法定比例(10%)
    3. 差异 = 应计提 - 账面已计提
    4. 累计法定盈余公积 ≥ 注册资本50% → 可不再计提

    如果未提供 net_profit，则尝试从 M6 底稿数据中读取净利润/计提基数。

    Body: { net_profit?, prior_year_loss, booked_accrual, accumulated_reserve, registered_capital, rate }
    Returns: AccrualTestResponse

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import run_accrual_test

    result = await run_accrual_test(wp_id, request, db)
    return result
