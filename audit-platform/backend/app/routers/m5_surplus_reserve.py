"""M5 盈余公积 — 导入导出三级端点 + 计提测试API

4个端点：
- GET  /api/m5-surplus-reserve/{wp_id}/export-template    明细表空白模板xlsx
- GET  /api/m5-surplus-reserve/{wp_id}/export-data         当前数据xlsx
- POST /api/m5-surplus-reserve/{wp_id}/import-data         解析xlsx写入（multipart）
- POST /api/m5-surplus-reserve/{wp_id}/accrual-test        法定盈余公积计提测试

科目编码: 4101盈余公积（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（法定计提在贷方增加，转增/弥补在借方减少）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 6.6, 4.3
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

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m5-surplus-reserve",
    tags=["M5 盈余公积"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class AccrualTestRequest(BaseModel):
    """计提测试请求"""
    net_profit: float = Field(0.0, description="本期净利润")
    prior_loss_offset: float = Field(0.0, description="弥补以前年度亏损（正数）")
    statutory_rate: float = Field(0.1, description="法定计提比例（默认10%）")
    discretionary_rate: float = Field(0.0, description="任意计提比例")
    statutory_booked: float = Field(0.0, description="法定账面计提")
    discretionary_booked: float = Field(0.0, description="任意账面计提")
    accumulated_statutory: float = Field(0.0, description="累计法定盈余公积")
    registered_capital: float = Field(0.0, description="注册资本")


class AccrualTestResponse(BaseModel):
    """计提测试响应"""
    accrual_base: float = Field(description="计提基数=净利润-弥补亏损")
    statutory_estimated: float = Field(description="法定应计提")
    statutory_diff: float = Field(description="法定计提差异")
    discretionary_estimated: float = Field(description="任意应计提")
    discretionary_diff: float = Field(description="任意计提差异")
    total_estimated: float = Field(description="合计应计提")
    total_diff: float = Field(description="合计差异")
    ceiling_reached: bool = Field(description="是否达50%上限")


# ═══════════════════════════════════════════════════════════════════════════════
# 跨底稿联动：M6净利润 → M5计提基数
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/m6-net-profit")
async def m5_fetch_m6_net_profit(
    wp_id: str,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """从M6未分配利润底稿获取净利润/计提基数

    跨底稿联动（Req 4.2）：
    - M6未分配利润的净利润/计提基数 → M5盈余公积计提检查
    - 计提基数 = 净利润 - 弥补以前年度亏损

    Query params:
        project_id: 项目ID（用于查找同项目下的M6底稿）

    Returns:
        { net_profit, prior_loss_offset, accrual_base, source_wp_id, ready, message }
    """
    from app.services.m5_surplus_reserve_service import fetch_m6_net_profit

    return await fetch_m6_net_profit(project_id, db)


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
    """导出空白xlsx模板（M5-2明细表：法定+任意盈余公积）

    Query params:
        sheet: 可选，指定导出单个sheet（M5-2）

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import generate_export_template

    buffer = await generate_export_template(wp_id, db, sheet=sheet)
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
    """导出含当前数据的xlsx（M5-2明细表）

    Query params:
        sheet: 可选，指定导出单个sheet

    Requirements: 6.6
    """
    from app.services.m5_surplus_reserve_service import generate_export_data

    buffer = await generate_export_data(wp_id, db, sheet=sheet)
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
    """导入xlsx解析写入checklist_responses（M5-2 明细表）

    Query params:
        sheet: 可选，指定导入目标sheet（M5-2）

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
# 计提测试 API
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/accrual-test")
async def m5_accrual_test(
    wp_id: str,
    request: AccrualTestRequest,
    current_user: User = Depends(get_current_user),
) -> AccrualTestResponse:
    """法定盈余公积计提测试

    计算逻辑：
    - 计提基数 = 净利润 - 弥补以前年度亏损
    - 法定应计提 = 基数 × 10%（法定比例）
    - 任意应计提 = 基数 × 任意比例
    - 计提差异 = 应计提 - 账面计提
    - 50%上限: 累计法定盈余公积 ≥ 注册资本 × 50%

    Body: AccrualTestRequest
    Returns: AccrualTestResponse

    Requirements: 4.3, 6.1
    """
    from app.services.m5_surplus_reserve_service import run_accrual_test

    result = run_accrual_test(
        net_profit=request.net_profit,
        prior_loss_offset=request.prior_loss_offset,
        statutory_rate=request.statutory_rate,
        discretionary_rate=request.discretionary_rate,
        statutory_booked=request.statutory_booked,
        discretionary_booked=request.discretionary_booked,
        accumulated_statutory=request.accumulated_statutory,
        registered_capital=request.registered_capital,
    )
    return AccrualTestResponse(**result)
