"""审计调整分录 API

覆盖：
- GET  列表（支持 type/status 筛选）
- POST 创建
- PUT  修改
- DELETE 软删除
- POST review 变更状态
- GET  summary 汇总统计
- GET  account-dropdown 科目下拉
- GET  wp-summary/{wp_code} 底稿审定表数据
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bulk_operations import BulkRequest, bulk_execute
from app.core.database import get_db
from app.core.pagination import PaginationParams
from app.deps import get_current_user, check_consol_lock, require_project_access, get_user_scope_cycles
from app.models.core import User
from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentType,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.audit_platform_schemas import (
    AccountOption,
    AdjustmentCreate,
    AdjustmentSummary,
    AdjustmentUpdate,
    ReviewStatusChange,
    WPAdjustmentSummary,
)
from app.services.adjustment_service import AdjustmentService
from app.services.mapping_service import get_codes_by_cycles
from app.services.misstatement_service import UnadjustedMisstatementService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/adjustments",
    tags=["adjustments"],
)


@router.get("")
async def list_adjustments(
    project_id: UUID,
    year: int = Query(...),
    adjustment_type: AdjustmentType | None = Query(None),
    review_status: ReviewStatus | None = Query(None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """分录列表（支持 type/status 筛选，需项目成员权限）"""
    svc = AdjustmentService(db)
    result = await svc.list_entries(
        project_id, year,
        adjustment_type=adjustment_type,
        review_status=review_status,
        page=pagination.page, page_size=pagination.page_size,
    )

    # scope_cycles 过滤：非 admin/partner 用户只能看到被分配循环对应的科目
    try:
        scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
        if scope_cycles is not None:
            allowed_codes = await get_codes_by_cycles(project_id, scope_cycles)
            if isinstance(result, dict) and "items" in result:
                result["items"] = [
                    e for e in result["items"]
                    if any(
                        li.get("standard_account_code") in allowed_codes
                        for li in (e.get("line_items") or [])
                    )
                ]
                result["total"] = len(result["items"])
    except Exception:
        pass  # scope filtering failure should not block the response

    return result


@router.post("")
async def create_adjustment(
    project_id: UUID,
    data: AdjustmentCreate,
    batch_mode: bool = Query(False, description="批量模式：暂不触发重算事件"),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """创建调整分录（合并锁定期间禁止，需编辑权限）"""
    svc = AdjustmentService(db)
    try:
        result = await svc.create_entry(project_id, data, user.id, batch_mode=batch_mode)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch-commit")
async def batch_commit(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
):
    """批量提交：统一触发一次重算事件（配合 batch_mode=true 使用）"""
    svc = AdjustmentService(db)
    result = await svc.batch_commit(project_id, year)
    return result


@router.put("/{entry_group_id}")
async def update_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    data: AdjustmentUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("edit")),
    _lock_check=Depends(check_consol_lock),
):
    """修改调整分录（合并锁定期间禁止，需编辑权限）"""
    svc = AdjustmentService(db)
    try:
        result = await svc.update_entry(project_id, entry_group_id, data, user.id)
        await db.commit()
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{entry_group_id}")
async def delete_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    db: AsyncSession = Depends(get_db),
    _lock_check=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    """软删除调整分录（合并锁定期间禁止，需编辑权限）"""
    svc = AdjustmentService(db)
    try:
        await svc.delete_entry(project_id, entry_group_id)
        await db.commit()
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/batch-delete")
async def batch_delete_adjustments(
    project_id: UUID,
    body: BulkRequest,
    db: AsyncSession = Depends(get_db),
    _lock_check=Depends(check_consol_lock),
    current_user: User = Depends(require_project_access("edit")),
):
    """批量软删除调整分录（合并锁定期间禁止，需编辑权限）"""
    svc = AdjustmentService(db)

    async def _delete_one(_db, _row):
        # 复用 service 层的删除逻辑（含状态校验+事件发布）
        await svc.delete_entry(project_id, _row.id)

    from app.models.audit_platform_models import Adjustment
    result = await bulk_execute(db, Adjustment, body.ids, _delete_one)
    await db.commit()
    return result


@router.post("/{entry_group_id}/review")
async def review_adjustment(
    project_id: UUID,
    entry_group_id: UUID,
    change: ReviewStatusChange,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("review")),
):
    """变更复核状态（需复核权限）"""
    svc = AdjustmentService(db)
    try:
        await svc.change_review_status(
            project_id, entry_group_id, change, user.id
        )
        await db.commit()
        return {"message": "状态变更成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# R1 需求 3 — AJE 一键转错报
# ---------------------------------------------------------------------------


class ConvertToMisstatementRequest(BaseModel):
    """将 rejected AJE 组转为未更正错报的请求体。"""

    force: bool = Field(
        default=False,
        description="当该 AJE 组已存在对应错报时是否强制再建一条（默认否，返回 409）",
    )


@router.post("/{entry_group_id}/convert-to-misstatement")
async def convert_adjustment_to_misstatement(
    project_id: UUID,
    entry_group_id: UUID,
    body: ConvertToMisstatementRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
):
    """将被驳回的 AJE 组一键转为《未更正错报汇总表》的一条记录。

    对齐 R1 需求 3 验收 7 与 gate 规则 `R1-AJE-UNCONVERTED` 的 suggested_action。
    封装 `UnadjustedMisstatementService.create_from_rejected_aje`，并补：
      - 组存在性 / 项目归属校验（400）
      - 幂等：已转过则返回 409 `ALREADY_CONVERTED`（可通过 force=true 强制再建）
      - year 从 group 内实际分录推断（不信任请求）
      - 审计日志 `adjustment.converted_to_misstatement`（失败仅 warning）
    """
    force = bool(body.force) if body else False

    # 1) 校验 group 存在且属于该项目
    group_rows = (
        await db.execute(
            sa.select(Adjustment.id, Adjustment.year, Adjustment.adjustment_type)
            .where(
                Adjustment.project_id == project_id,
                Adjustment.entry_group_id == entry_group_id,
                Adjustment.is_deleted.is_(False),
            )
        )
    ).all()
    if not group_rows:
        raise HTTPException(
            status_code=400,
            detail="AJE 组不存在或不属于该项目",
        )

    adj_ids = [r.id for r in group_rows]
    # year 取该组所有行 year 的一致值；如不一致打 warning 并取第一行
    years = {r.year for r in group_rows}
    if len(years) > 1:
        logger.warning(
            "[convert_to_misstatement] group=%s has inconsistent years %s, using first row",
            entry_group_id, sorted(years),
        )
    year = group_rows[0].year

    # 2) 幂等检查：查该组内任一 adjustment_id 是否已被错报引用
    existing_ms_row = (
        await db.execute(
            sa.select(UnadjustedMisstatement.id)
            .where(
                UnadjustedMisstatement.project_id == project_id,
                UnadjustedMisstatement.source_adjustment_id.in_(adj_ids),
                UnadjustedMisstatement.is_deleted.is_(False),
            )
            .limit(1)
        )
    ).first()

    if existing_ms_row and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "ALREADY_CONVERTED",
                "message": "该 AJE 组已转为未更正错报，如需再次转换请传入 force=true",
                "existing_misstatement_id": str(existing_ms_row.id),
            },
        )

    # 3) 调 service 落库
    svc = UnadjustedMisstatementService(db)
    try:
        result = await svc.create_from_rejected_aje(
            project_id=project_id,
            entry_group_id=entry_group_id,
            year=year,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4) 审计日志（失败仅 warning 不阻断）
    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=current_user.id,
            action="adjustment.converted_to_misstatement",
            object_type="adjustment_group",
            object_id=entry_group_id,
            project_id=project_id,
            details={
                "misstatement_id": str(result.id),
                "source_adjustment_id": str(result.source_adjustment_id)
                if result.source_adjustment_id
                else None,
                "adjustment_count": len(adj_ids),
                "net_amount": str(result.misstatement_amount),
                "misstatement_type": result.misstatement_type.value
                if hasattr(result.misstatement_type, "value")
                else str(result.misstatement_type),
                "force": force,
                "year": year,
            },
        )
    except Exception as log_err:  # noqa: BLE001
        logger.warning(
            "[convert_to_misstatement] audit log failed (non-blocking): %s",
            log_err,
        )

    await db.commit()

    return {
        "misstatement_id": str(result.id),
        "source_entry_group_id": str(entry_group_id),
        "source_adjustment_id": str(result.source_adjustment_id)
        if result.source_adjustment_id
        else None,
        "net_amount": str(result.misstatement_amount),
        "misstatement_type": result.misstatement_type.value
        if hasattr(result.misstatement_type, "value")
        else str(result.misstatement_type),
        "year": year,
        "adjustment_count": len(adj_ids),
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }


@router.get("/summary")
async def get_summary(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """汇总统计"""
    svc = AdjustmentService(db)
    result = await svc.get_summary(project_id, year)
    return result.model_dump()


@router.get("/account-dropdown")
async def get_account_dropdown(
    project_id: UUID,
    report_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """科目下拉选项"""
    svc = AdjustmentService(db)
    options = await svc.get_account_dropdown(project_id, report_line_code)
    return [o.model_dump() for o in options]


@router.get("/wp-summary/{wp_code}")
async def get_wp_summary(
    project_id: UUID,
    wp_code: str,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """底稿审定表数据"""
    svc = AdjustmentService(db)
    result = await svc.get_wp_adjustment_summary(project_id, year, wp_code)
    return result.model_dump()


@router.get("/export-summary")
async def export_adjustment_summary(
    project_id: UUID,
    year: int = Query(...),
    format: str = Query("excel", description="导出格式: excel 或 json"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """导出审计调整汇总表（AJE + RJE）"""
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(
        "adjustment_export: user=%s project=%s year=%s",
        str(current_user.id), str(project_id), year,
    )

    svc = AdjustmentService(db)
    aje_result = await svc.list_entries(project_id, year, adjustment_type=AdjustmentType.aje, page_size=500)
    rje_result = await svc.list_entries(project_id, year, adjustment_type=AdjustmentType.rje, page_size=500)
    aje_list = aje_result if isinstance(aje_result, list) else (aje_result.items if hasattr(aje_result, 'items') else [])
    rje_list = rje_result if isinstance(rje_result, list) else (rje_result.items if hasattr(rje_result, 'items') else [])

    if format == "json":
        return {
            "aje": [_adj_to_dict(a) for a in aje_list],
            "rje": [_adj_to_dict(a) for a in rje_list],
            "aje_count": len(aje_list),
            "rje_count": len(rje_list),
        }

    # Excel 导出
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
    except ImportError:
        raise HTTPException(500, "openpyxl 未安装")

    wb = openpyxl.Workbook()

    # AJE sheet
    ws_aje = wb.active
    ws_aje.title = "AJE审计调整"
    _write_adj_sheet(ws_aje, aje_list, "AJE")

    # RJE sheet
    ws_rje = wb.create_sheet("RJE重分类")
    _write_adj_sheet(ws_rje, rje_list, "RJE")

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=adjustment_summary_{year}.xlsx"},
    )


def _adj_to_dict(adj) -> dict:
    return {
        "adjustment_no": adj.adjustment_no if hasattr(adj, 'adjustment_no') else str(adj.get('adjustment_no', '')),
        "description": adj.description if hasattr(adj, 'description') else str(adj.get('description', '')),
        "account_code": adj.account_code if hasattr(adj, 'account_code') else str(adj.get('account_code', '')),
        "account_name": adj.account_name if hasattr(adj, 'account_name') else str(adj.get('account_name', '')),
        "debit_amount": str(adj.debit_amount) if hasattr(adj, 'debit_amount') else str(adj.get('debit_amount', 0)),
        "credit_amount": str(adj.credit_amount) if hasattr(adj, 'credit_amount') else str(adj.get('credit_amount', 0)),
    }


def _write_adj_sheet(ws, entries, adj_type: str):
    from openpyxl.styles import Font, Alignment, PatternFill

    headers = ["编号", "摘要", "科目编码", "科目名称", "借方金额", "贷方金额"]
    header_fill = PatternFill(start_color="F4F0FA", end_color="F4F0FA", fill_type="solid")
    header_font = Font(bold=True, size=11)

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for i, adj in enumerate(entries, 2):
        d = _adj_to_dict(adj)
        ws.cell(row=i, column=1, value=d["adjustment_no"])
        ws.cell(row=i, column=2, value=d["description"])
        ws.cell(row=i, column=3, value=d["account_code"])
        ws.cell(row=i, column=4, value=d["account_name"])
        ws.cell(row=i, column=5, value=float(d["debit_amount"] or 0))
        ws.cell(row=i, column=6, value=float(d["credit_amount"] or 0))

    # 列宽
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 16
