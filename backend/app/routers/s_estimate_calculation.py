"""S 类计算型底稿 — TB 回写 + 自动取数 + 导入导出三级端点.

端点：
- POST /api/s-estimate/{wp_id}/tb-writeback          单科目审定数回写（flush，上层 commit）
- POST /api/s-estimate/{wp_id}/tb-writeback-batch    批量回写
- GET  /api/s-estimate/{wp_id}/auto-data             自动取数（auto_data_source + field_overrides）
- GET  /api/s-estimate/{wp_id}/export-template       导出空白xlsx模板（按sheet分导出）
- GET  /api/s-estimate/{wp_id}/export-data           导出当前数据xlsx
- POST /api/s-estimate/{wp_id}/import-data           解析xlsx写入（multipart）

适用 componentType: s3-policy-change / s15-eps-roe / s20-revenue-deduction / s21-data-asset
回写口径: v2 正数（audited_amount 始终正数存储）
关键约束: service 层仅 flush 不 commit，由本 router 统一 commit
导入导出: RFC5987 中文文件名编码 / 多区块分 sheet 导出

Requirements: 7.1, 7.2, 7.4, 10.1, 10.2, 10.3, 10.4
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.s_estimate_tb_writeback_service import (
    S_ESTIMATE_COMPONENT_TYPES,
    SEstimateTBWritebackService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/s-estimate",
    tags=["S 类计算型底稿"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class TBWritebackRequest(BaseModel):
    """TB 回写请求（单科目）"""
    account_code: str = Field(description="标准科目编码")
    audited_amount: float = Field(description="审定金额（v2 正数口径）")
    component_type: str | None = Field(
        None,
        description="来源 componentType（可选，用于校验合法性）",
    )


class TBWritebackResponse(BaseModel):
    """TB 回写响应"""
    message: str = Field("回写成功")
    account_code: str = Field(description="科目编码")
    audited_amount: str = Field(description="回写后审定金额")
    previous_amount: str | None = Field(None, description="回写前审定金额")


class TBWritebackBatchRequest(BaseModel):
    """TB 批量回写请求"""
    rows: list[dict[str, Any]] = Field(
        description="[{'account_code': str, 'audited_amount': float}, ...]",
    )
    component_type: str | None = Field(
        None,
        description="来源 componentType（可选）",
    )


class TBWritebackBatchResponse(BaseModel):
    """TB 批量回写响应"""
    message: str = Field("批量回写完成")
    total: int = Field(description="总行数")
    success_count: int = Field(description="成功行数")
    results: list[dict[str, Any]] = Field(description="各行结果")


class AutoDataRequest(BaseModel):
    """自动取数请求"""
    component_type: str = Field(description="componentType")
    field_overrides: dict[str, Any] | None = Field(
        None,
        description="用户覆盖字段（优先级最高）",
    )


class AutoDataResponse(BaseModel):
    """自动取数响应"""
    auto_resolved: dict[str, Any] = Field(
        default_factory=dict,
        description="resolver 自动解析结果",
    )
    overrides_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="实际应用的覆盖字段",
    )
    final: dict[str, Any] = Field(
        default_factory=dict,
        description="最终合并后的数据",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TB 回写（单科目）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/tb-writeback")
async def s_estimate_tb_writeback(
    wp_id: str,
    request: TBWritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackResponse:
    """S 类审定金额回写 trial_balance（v2 正数口径）.

    service 层仅 flush，由本端点统一 commit。
    前端调用方：GtS3PolicyChange / GtS15EpsRoe / GtS20RevenueDeduction / GtS21DataAsset
    各自的 useXFormData.writebackTB(amount) composable。

    Requirements: 7.1, 7.4
    """
    from uuid import UUID as _UUID

    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：审定数回写 trial_balance（写副作用）之前完成授权判定
    # （Req 8.5 / trial-balance writeback）。tb_writeback 仅 lead/admin/supervisor_scope；
    # gate 从 wp_id 反查 project；越权/不存在统一 404。
    try:
        _wpid = _UUID(str(wp_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="资源不存在或不可访问")
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.tb_writeback", action="tb_writeback", method="POST",
        wp_id=_wpid, entry_family="save",
        route_name="/api/s-estimate/{wp_id}/tb-writeback",
    )
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_paper wp "
            "JOIN projects p ON p.id = wp.project_id "
            "WHERE wp.id = :wp_id"
        ),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    project_id = wp_row[0]
    year = int(wp_row[1]) if wp_row[1] else 0

    if not year:
        raise HTTPException(400, "无法确定审计年度")

    # Service 层：flush only
    svc = SEstimateTBWritebackService(db)
    try:
        result = await svc.writeback_audited_amount(
            project_id=project_id,
            year=year,
            account_code=request.account_code,
            audited_amount=request.audited_amount,
            component_type=request.component_type,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))

    # 上层统一 commit（Requirements 7.4 — service 层仅 flush）
    await db.commit()

    # ─── 发布 WORKPAPER_SAVED 事件（Requirements 7.3）───────────────────────
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project_id,
            year=year,
            extra={
                "wp_id": wp_id,
                "wp_code": request.component_type or "",
                "trigger": "s_estimate_tb_writeback",
                "account_code": request.account_code,
                "audited_amount": str(request.audited_amount),
            },
        ))
    except Exception as e:
        logger.warning("S-estimate WORKPAPER_SAVED publish failed wp=%s: %s", wp_id, e)

    return TBWritebackResponse(
        message="回写成功",
        account_code=result["account_code"],
        audited_amount=result["audited_amount"],
        previous_amount=result.get("previous_amount"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TB 批量回写
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/tb-writeback-batch")
async def s_estimate_tb_writeback_batch(
    wp_id: str,
    request: TBWritebackBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackBatchResponse:
    """S 类审定金额批量回写（多科目同时写入）.

    service 层每行仅 flush，全部完成后统一 commit。

    Requirements: 7.1, 7.4
    """
    from uuid import UUID as _UUID

    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：批量审定回写（写副作用）之前完成授权判定（Req 8.5 / tb writeback）。
    try:
        _wpid = _UUID(str(wp_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="资源不存在或不可访问")
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.tb_writeback", action="tb_writeback", method="POST",
        wp_id=_wpid, entry_family="save",
        route_name="/api/s-estimate/{wp_id}/tb-writeback-batch",
    )
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_paper wp "
            "JOIN projects p ON p.id = wp.project_id "
            "WHERE wp.id = :wp_id"
        ),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    project_id = wp_row[0]
    year = int(wp_row[1]) if wp_row[1] else 0

    if not year:
        raise HTTPException(400, "无法确定审计年度")

    svc = SEstimateTBWritebackService(db)
    results = await svc.writeback_batch(
        project_id=project_id,
        year=year,
        rows=request.rows,
        component_type=request.component_type,
    )

    # 统一 commit
    await db.commit()

    success_count = sum(1 for r in results if "error" not in r)

    # ─── 发布 WORKPAPER_SAVED 事件（Requirements 7.3）───────────────────────
    if success_count > 0:
        try:
            from app.models.audit_platform_schemas import EventPayload, EventType
            from app.services.event_bus import event_bus

            await event_bus.publish(EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project_id,
                year=year,
                extra={
                    "wp_id": wp_id,
                    "wp_code": request.component_type or "",
                    "trigger": "s_estimate_tb_writeback_batch",
                    "batch_size": len(results),
                    "success_count": success_count,
                },
            ))
        except Exception as e:
            logger.warning("S-estimate batch WORKPAPER_SAVED publish failed wp=%s: %s", wp_id, e)

    return TBWritebackBatchResponse(
        message=f"批量回写完成: {success_count}/{len(results)} 成功",
        total=len(results),
        success_count=success_count,
        results=results,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 自动取数（auto_data_source + field_overrides）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/auto-data")
async def s_estimate_auto_data(
    wp_id: str,
    request: AutoDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoDataResponse:
    """S 类自动取数：通过 resolver 获取未审数+调整分录，用户可 field_overrides 覆盖.

    优先级: 即时 field_overrides > 持久化 field_overrides > resolver 自动值

    Requirements: 7.2
    """
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_paper wp "
            "JOIN projects p ON p.id = wp.project_id "
            "WHERE wp.id = :wp_id"
        ),
        {"wp_id": wp_id},
    )
    wp_row = wp_result.fetchone()
    if not wp_row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    project_id = wp_row[0]
    year = int(wp_row[1]) if wp_row[1] else 0

    if not year:
        raise HTTPException(400, "无法确定审计年度")

    svc = SEstimateTBWritebackService(db)
    try:
        result = await svc.resolve_auto_data(
            project_id=project_id,
            year=year,
            component_type=request.component_type,
            field_overrides=request.field_overrides,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return AutoDataResponse(**result)


# ═══════════════════════════════════════════════════════════════════════════════
# 导入导出三级端点（Requirements: 10.1, 10.2, 10.3, 10.4）
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def s_estimate_export_template(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（S21-2/S20-unrelated/S20-noSubstance）

    Query params:
        sheet: 可选，指定导出sheet（S21-2/S20-unrelated/S20-noSubstance）
               不传则导出全部 sheet（多区块分 sheet — Req 10.3）

    RFC5987 中文文件名（Req 10.4）
    Requirements: 10.1, 10.3, 10.4
    """
    from app.services.s_estimate_import_export_service import (
        export_template,
        get_sheet_filename,
    )

    buffer = await export_template(wp_id, db, sheet=sheet)
    filename = get_sheet_filename(sheet or "全部", "模板")
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.get("/{wp_id}/export-data")
async def s_estimate_export_data(
    wp_id: str,
    sheet: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx（S21-2/S20-unrelated/S20-noSubstance）

    Query params:
        sheet: 可选，指定导出 sheet
               不传则导出全部 sheet（多区块分 sheet — Req 10.3）

    RFC5987 中文文件名（Req 10.4）
    Requirements: 10.1, 10.3, 10.4
    """
    from app.services.s_estimate_import_export_service import (
        export_data,
        get_sheet_filename,
    )

    buffer = await export_data(wp_id, db, sheet=sheet)
    filename = get_sheet_filename(sheet or "全部", "数据")
    encoded_filename = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.post("/{wp_id}/import-data")
async def s_estimate_import_data(
    wp_id: str,
    sheet: str | None = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses（S21-2/S20动态行明细）

    Query params:
        sheet: 可选，指定导入目标 sheet（S21-2/S20-unrelated/S20-noSubstance）

    Returns:
        { imported_count: int, warnings: list[str] }

    Requirements: 10.1, 10.2
    """
    from app.services.s_estimate_import_export_service import import_data

    content = await file.read()
    try:
        result = await import_data(wp_id, content, db, sheet=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return result
