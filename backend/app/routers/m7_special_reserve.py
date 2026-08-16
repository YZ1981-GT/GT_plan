"""M7 专项储备 — 导入导出三级端点 + 计提测试API

4个端点：
- GET  /api/m7-special-reserve/{wp_id}/export-template    明细表空白模板xlsx
- GET  /api/m7-special-reserve/{wp_id}/export-data         当前数据xlsx
- POST /api/m7-special-reserve/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m7-special-reserve/{wp_id}/accrual-test        安全生产费计提测试

科目编码: 4201专项储备（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（计提在贷方增加，使用在借方减少）
安全生产费: 高危行业按产量分档计提 / 其他按营业收入比例计提
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 7.6
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
    prefix="/api/m7-special-reserve",
    tags=["M7 专项储备"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# X-3 调整分录汇总表 —— 形态 A 三态（spec x3-adjustment-entry-import-export 任务 5.1）
# ═══════════════════════════════════════════════════════════════════════════════

#: 本模块的短前缀 = catalog `import_export.api_prefix`，单份 UI 与批量两条通路共用它。
_IE_API_PREFIX = "m7"

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
#:
#: 🔴 另一条存量缺陷（G6 已登记为 `SERVICE_MODULE_MISSING`）：本模块既有三态端点惰性 import
#:    的 service 模块在仓库中**不存在** ⇒ 那三个端点一调即 ImportError。形态 A 三态走共享实现
#:    `_x3_adjustment_import_export`，与该 service 无关，故本模块 import 与形态 A 调用均不受影响。
IE_SHEETS: frozenset[str] = _X3_CODES

attach_shape_a_routes(router, api_prefix=_IE_API_PREFIX, sheets=_X3_CODES)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class AccrualTier(BaseModel):
    """按产量分档计提条目"""
    output: float = Field(description="产量（吨/万吨）")
    rate: float = Field(description="计提标准（元/吨）")


class AccrualTestRequest(BaseModel):
    """安全生产费计提测试请求"""
    method: str = Field("output", description="计提方式: output(按产量) / revenue(按营业收入)")
    tiers: list[AccrualTier] = Field(default_factory=list, description="按产量分档计提明细")
    revenue: float = Field(0.0, description="营业收入（按收入计提时使用）")
    revenue_rate: float = Field(0.0, description="营业收入计提比例")
    booked_accrual: float = Field(0.0, description="账面已计提金额")


class AccrualTestResponse(BaseModel):
    """安全生产费计提测试响应"""
    method: str = Field(description="计提方式")
    estimated: float = Field(description="应计提金额")
    booked: float = Field(description="账面计提")
    diff: float = Field(description="计提差异=应计提-账面")
    is_material: bool = Field(description="差异是否重大（|diff|>阈值）")
    detail: dict[str, Any] = Field(default_factory=dict, description="计算明细")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m7_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（M7-2明细表 / M7-4计提测试表）

    Query params:
        sheet: 可选，指定导出sheet（M7-2/M7-4/M7-5）

    Requirements: 7.6
    """
    from app.services.m7_special_reserve_service import generate_export_template

    buffer = await generate_export_template(wp_id, db, sheet=sheet)
    filename = f"M7专项储备_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m7_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（M7-2明细/M7-4计提测试）

    Query params:
        sheet: 可选，指定导出sheet

    Requirements: 7.6
    """
    from app.services.m7_special_reserve_service import generate_export_data

    buffer = await generate_export_data(wp_id, db, sheet=sheet)
    filename = f"M7专项储备_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m7_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（M7-2明细表动态行）

    Query params:
        sheet: 可选，指定导入目标sheet（M7-2/M7-4）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 7.6
    """
    from app.services.m7_special_reserve_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 安全生产费计提测试 API
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/accrual-test")
async def m7_accrual_test(
    wp_id: str,
    request: AccrualTestRequest,
    current_user: User = Depends(get_current_user),
) -> AccrualTestResponse:
    """安全生产费计提测试

    计算逻辑：
    - 按产量: 应计提 = Σ(各档产量 × 档位标准)
    - 按收入: 应计提 = 营业收入 × 计提比例
    - 计提差异 = 应计提 - 账面计提
    - 重大性判断: |差异| > 阈值

    Body: AccrualTestRequest
    Returns: AccrualTestResponse

    Requirements: 4.2-4.4, 7.1-7.3
    """
    from app.services.m7_special_reserve_service import run_accrual_test

    result = run_accrual_test(
        method=request.method,
        tiers=[{"output": t.output, "rate": t.rate} for t in request.tiers],
        revenue=request.revenue,
        revenue_rate=request.revenue_rate,
        booked_accrual=request.booked_accrual,
    )
    return AccrualTestResponse(**result)
