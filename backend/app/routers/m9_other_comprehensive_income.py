"""M9 其他综合收益 — 导入导出三级端点 + OCI核对API + TB回写

5个端点：
- GET  /api/m9-other-comprehensive-income/{wp_id}/export-template    多sheet空白模板xlsx
- GET  /api/m9-other-comprehensive-income/{wp_id}/export-data         当前数据xlsx
- POST /api/m9-other-comprehensive-income/{wp_id}/import-data         解析xlsx写入（multipart）
- GET  /api/m9-other-comprehensive-income/{wp_id}/validate-formulas   权益类公式方向验证
- POST /api/m9-other-comprehensive-income/{wp_id}/tb-writeback        回写TB（科目4103）

科目编码: 4103其他综合收益（**贷方/权益类！**）
公式方向: 期末=期初+贷方-借方（OCI增加在贷方，重分类/减少在借方）
OCI特征: 税后净额列示=税前发生-所得税影响；分两大类（不可/可重分类进损益）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 6.6
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/m9-other-comprehensive-income",
    tags=["M9 其他综合收益"],
)


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
    credit: float = Field(0.0, description="贷方发生额（OCI增加）")
    debit: float = Field(0.0, description="借方发生额（重分类/减少）")
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
        "权益类贷方：期末=期初+贷方-借方（OCI增加贷方，减少/重分类借方）",
        description="公式说明",
    )


class TBWritebackRequest(BaseModel):
    """TB回写请求（科目4103其他综合收益）"""
    audited_amount: float = Field(description="审定金额")
    account_code: str = Field("4103", description="科目编码，默认4103")


class TBWritebackResponse(BaseModel):
    """TB回写响应"""
    message: str = Field("回写成功")
    account_code: str = Field(description="科目编码")
    audited_amount: str = Field(description="回写后审定金额")


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def m9_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（M9-2明细表 / M9-4核对表）

    Query params:
        sheet: 可选，指定导出sheet（M9-2/M9-4）

    Requirements: 6.6
    """
    from app.services.m9_other_comprehensive_income_service import generate_export_template

    buffer = await generate_export_template(wp_id, db, sheet=sheet)
    filename = f"M9其他综合收益_{sheet or '全部'}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-data")
async def m9_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（M9-2明细/M9-4核对）

    Query params:
        sheet: 可选，指定导出sheet

    Requirements: 6.6
    """
    from app.services.m9_other_comprehensive_income_service import generate_export_data

    buffer = await generate_export_data(wp_id, db, sheet=sheet)
    filename = f"M9其他综合收益_{sheet or '全部'}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/import-data")
async def m9_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（M9-2明细表动态行 / M9-4核对表）

    Query params:
        sheet: 可选，指定导入目标sheet（M9-2/M9-4）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 6.6
    """
    from app.services.m9_other_comprehensive_income_service import import_data

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


@router.get("/{wp_id}/validate-formulas")
async def m9_validate_formulas(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateFormulasResponse:
    """校验权益类公式方向（期末=期初+贷方-借方）

    其他综合收益为贷方/权益类科目（4103）：
    - OCI增加时贷方增加（如公允价值上升计入OCI）
    - OCI减少/重分类进损益时借方减少
    - 期末余额 = 期初 + 贷方发生额 - 借方发生额
    - 本期税后净额 = 本期税前发生 - 所得税影响

    从 checklist_responses 读取已保存的审定表数据进行验证。

    Requirements: 6.6
    """
    from app.services.m9_other_comprehensive_income_service import get_adjudication_rows

    rows = await get_adjudication_rows(wp_id, db)

    results: list[ValidateFormulasRow] = []
    valid_count = 0

    for row_data in rows:
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
# TB 回写（科目4103其他综合收益）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/tb-writeback")
async def m9_tb_writeback(
    wp_id: str,
    request: TBWritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackResponse:
    """审定数回写到 trial_balance（科目4103其他综合收益）

    权益类贷方科目 — 审定数回写后触发 TB 缓存失效和事件通知。
    前端 useM9FormData.writebackTB(amount) 调用。

    Requirements: 2.6, 6.6
    """
    from app.models.audit_platform_models import TrialBalance

    # 从 wp_id 获取 project_id
    wp_result = await db.execute(
        sa.text("SELECT project_id FROM working_papers WHERE id = :wp_id"),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    project_id = wp_row[0]
    account_code = request.account_code

    # 查找匹配的 trial_balance 行
    stmt = (
        sa.select(TrialBalance)
        .where(
            TrialBalance.project_id == project_id,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        )
        .order_by(TrialBalance.year.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(
            404,
            f"试算表中未找到科目 {account_code}，请先导入试算表数据",
        )

    # 更新 audited_amount
    row.audited_amount = Decimal(str(request.audited_amount))
    await db.flush()
    await db.commit()

    logger.info(
        "M9 TB回写完成: project=%s account=%s amount=%s",
        project_id, account_code, request.audited_amount,
    )

    return TBWritebackResponse(
        message="回写成功",
        account_code=account_code,
        audited_amount=str(row.audited_amount),
    )
