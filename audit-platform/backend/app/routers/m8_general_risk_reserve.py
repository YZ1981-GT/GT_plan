"""M8 一般风险准备 — 导入导出三级端点 + 风险计提测试API

5个端点：
- GET  /api/m8-general-risk-reserve/{wp_id}/export-template    明细表空白模板xlsx
- GET  /api/m8-general-risk-reserve/{wp_id}/export-data         当前数据xlsx
- POST /api/m8-general-risk-reserve/{wp_id}/import-data         解析xlsx写入（multipart）
- GET  /api/m8-general-risk-reserve/{wp_id}/validate-formulas   公式一致性验证
- POST /api/m8-general-risk-reserve/{wp_id}/risk-provision-test 风险资产计提测试

科目编码: 4104一般风险准备（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（计提在贷方增加，转回在借方减少）
金融企业专属: 按风险资产期末余额×比例（原则上不低于1.5%）
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

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m8-general-risk-reserve",
    tags=["M8 一般风险准备"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class RiskAssetItem(BaseModel):
    """风险资产条目"""
    name: str = Field("", description="项目名称")
    risk_asset_balance: float = Field(0.0, description="风险资产期末余额")
    provision_rate: float = Field(0.015, description="计提比例（默认1.5%）")
    booked_balance: float = Field(0.0, description="账面一般风险准备余额（计提金额）")


class RiskProvisionTestRequest(BaseModel):
    """风险资产计提测试请求"""
    items: list[RiskAssetItem] = Field(
        default_factory=list,
        description="各项风险资产明细",
    )
    threshold: float = Field(0.0, description="差异阈值（可选）")


class RiskProvisionTestResponse(BaseModel):
    """风险资产计提测试响应"""
    items: list[dict[str, Any]] = Field(description="各项计算结果")
    summary: dict[str, Any] = Field(description="汇总结果")


class FormulaValidationResponse(BaseModel):
    """公式一致性验证响应"""
    valid: bool = Field(description="是否一致")
    checks: list[dict[str, Any]] = Field(description="各项校验结果")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m8_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（M8-2明细表 / M8-4风险测试表）

    Query params:
        sheet: 可选，指定导出sheet（M8-2/M8-4）

    Requirements: 6.6
    """
    from app.services.m8_general_risk_reserve_service import export_template

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = f"M8一般风险准备_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m8_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（M8-2明细/M8-4风险测试）

    Query params:
        sheet: 可选，指定导出sheet

    Requirements: 6.6
    """
    from app.services.m8_general_risk_reserve_service import export_data

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = f"M8一般风险准备_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m8_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（M8-2明细表动态行）

    Query params:
        sheet: 可选，指定导入目标sheet（M8-2/M8-4）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.6
    """
    from app.services.m8_general_risk_reserve_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 公式一致性验证
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/validate-formulas")
async def m8_validate_formulas(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FormulaValidationResponse:
    """验证公式一致性（审定表vs明细表 / 计提测试差异）

    校验内容：
    - M8-1审定表合计 vs M8-2明细表合计
    - M8-4计提测试：应计金额=风险资产×比例
    - 权益类方向：期末=期初+贷方-借方

    Requirements: 6.6
    """
    from app.services.m8_general_risk_reserve_service import validate_risk_provision

    result = await validate_risk_provision(db, wp_id)
    return FormulaValidationResponse(**result)


# ═══════════════════════════════════════════════════════════════════════════════
# 风险资产计提测试 API
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/risk-provision-test")
async def m8_risk_provision_test(
    wp_id: str,
    request: RiskProvisionTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskProvisionTestResponse:
    """风险资产计提测试

    计算逻辑（M8-4核心公式）：
    - 应计金额 = 风险资产期末余额 × 计提比例（原则上≥1.5%）
    - 差异 = 账面计提 - 应计金额
    - 汇总：各项风险资产合计

    Body: RiskProvisionTestRequest
    Returns: RiskProvisionTestResponse

    Requirements: 3.4
    """
    from app.services.m8_general_risk_reserve_service import get_risk_provision_summary

    result = get_risk_provision_summary(
        items=[item.model_dump() for item in request.items],
        threshold=request.threshold,
    )
    return RiskProvisionTestResponse(**result)
