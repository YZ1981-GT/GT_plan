"""S 类交易型底稿 — TB 回写 + 自动取数 + 披露联动端点.

端点：
- POST /api/s-transaction/{wp_id}/tb-writeback          单科目审定数回写（flush，上层 commit）
- POST /api/s-transaction/{wp_id}/tb-writeback-batch    批量回写
- POST /api/s-transaction/{wp_id}/auto-data             自动取数（auto_data_source + field_overrides）
- POST /api/s-transaction/{wp_id}/disclosure-notify     披露文本更新通知（触发 disclosure:note-text-updated）

适用底稿: S4/S5/S6/S8/S9/S10（含审定表的 S 类交易型底稿）
回写口径: v2 正数（audited_amount 始终正数存储）
关键约束: service 层仅 flush 不 commit，由本 router 统一 commit
EventBus: WORKPAPER_SAVED + disclosure:note-text-updated

Requirements: 9.1, 9.2, 9.3, 9.4
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.s_transaction_tb_writeback_service import (
    S_TRANSACTION_COMPONENT_TYPES,
    STransactionTBWritebackService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/s-transaction",
    tags=["S 类交易型底稿"],
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
    wp_code: str | None = Field(
        None,
        description="底稿编码 S4/S5/S6/S8/S9/S10（区分 a-program-console 中各底稿）",
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
    component_type: str | None = Field(None, description="来源 componentType（可选）")
    wp_code: str | None = Field(None, description="底稿编码 S4/S5/S6/S8/S9/S10")


class TBWritebackBatchResponse(BaseModel):
    """TB 批量回写响应"""
    message: str = Field("批量回写完成")
    total: int = Field(description="总行数")
    success_count: int = Field(description="成功行数")
    results: list[dict[str, Any]] = Field(description="各行结果")


class AutoDataRequest(BaseModel):
    """自动取数请求"""
    wp_code: str = Field(description="底稿编码 S4/S5/S6/S8/S9/S10")
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


class DisclosureNotifyRequest(BaseModel):
    """披露文本更新通知请求"""
    wp_code: str = Field(description="底稿编码 S4/S5")
    section: str = Field(default="non-recurring", description="附注章节标识")
    text: str = Field(default="", description="披露文本内容")


# ═══════════════════════════════════════════════════════════════════════════════
# TB 回写（单科目）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/tb-writeback")
async def s_transaction_tb_writeback(
    wp_id: str,
    request: TBWritebackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackResponse:
    """S 类交易型审定金额回写 trial_balance（v2 正数口径）.

    service 层仅 flush，由本端点统一 commit。
    适用底稿: S4/S5/S6/S8/S9/S10。

    Requirements: 9.1, 9.3
    """
    from uuid import UUID as _UUID

    from app.routers._wp_gate import enforce_wp_gate

    # Wp_Bound_Gate：审定数回写 trial_balance（写副作用）之前完成授权判定（Req 8.5 / tb writeback）。
    try:
        _wpid = _UUID(str(wp_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="资源不存在或不可访问")
    await enforce_wp_gate(
        db, current_user,
        entrypoint="workpaper.tb_writeback", action="tb_writeback", method="POST",
        wp_id=_wpid, entry_family="save",
        route_name="/api/s-transaction/{wp_id}/tb-writeback",
    )
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_papers wp "
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
    svc = STransactionTBWritebackService(db)
    try:
        result = await svc.writeback_audited_amount(
            project_id=project_id,
            year=year,
            account_code=request.account_code,
            audited_amount=request.audited_amount,
            component_type=request.component_type,
            wp_code=request.wp_code,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except LookupError as e:
        raise HTTPException(404, str(e))

    # 上层统一 commit（Requirements 9.3 — service 层仅 flush）
    await db.commit()

    # ─── 发布 WORKPAPER_SAVED 事件（Requirements 9.3）───────────────────────
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=project_id,
            year=year,
            extra={
                "wp_id": wp_id,
                "wp_code": request.wp_code or request.component_type or "",
                "trigger": "s_transaction_tb_writeback",
                "account_code": request.account_code,
                "audited_amount": str(request.audited_amount),
            },
        ))
    except Exception as e:
        logger.warning("S-transaction WORKPAPER_SAVED publish failed wp=%s: %s", wp_id, e)

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
async def s_transaction_tb_writeback_batch(
    wp_id: str,
    request: TBWritebackBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TBWritebackBatchResponse:
    """S 类交易型审定金额批量回写（多科目同时写入）.

    service 层每行仅 flush，全部完成后统一 commit。

    Requirements: 9.1, 9.3
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
        route_name="/api/s-transaction/{wp_id}/tb-writeback-batch",
    )
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_papers wp "
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

    svc = STransactionTBWritebackService(db)
    results = await svc.writeback_batch(
        project_id=project_id,
        year=year,
        rows=request.rows,
        component_type=request.component_type,
        wp_code=request.wp_code,
    )

    # 统一 commit
    await db.commit()

    success_count = sum(1 for r in results if "error" not in r)

    # ─── 发布 WORKPAPER_SAVED 事件（Requirements 9.3）───────────────────────
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
                    "wp_code": request.wp_code or request.component_type or "",
                    "trigger": "s_transaction_tb_writeback_batch",
                    "batch_size": len(results),
                    "success_count": success_count,
                },
            ))
        except Exception as e:
            logger.warning("S-transaction batch WORKPAPER_SAVED publish failed wp=%s: %s", wp_id, e)

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
async def s_transaction_auto_data(
    wp_id: str,
    request: AutoDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoDataResponse:
    """S 类交易型自动取数：通过 resolver 获取未审数+调整分录，用户可 field_overrides 覆盖.

    优先级: 即时 field_overrides > 持久化 field_overrides > resolver 自动值

    Requirements: 9.2
    """
    # 从 wp_id 获取 project_id + year
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_papers wp "
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

    svc = STransactionTBWritebackService(db)
    try:
        result = await svc.resolve_auto_data(
            project_id=project_id,
            year=year,
            wp_code=request.wp_code,
            field_overrides=request.field_overrides,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return AutoDataResponse(**result)


# ═══════════════════════════════════════════════════════════════════════════════
# 披露文本更新通知（Req 9.4 — S4/S5 非经常性损益）
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/{wp_id}/disclosure-notify")
async def s_transaction_disclosure_notify(
    wp_id: str,
    request: DisclosureNotifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """S4/S5 非经常性损益披露文本更新通知.

    前端发布 disclosure:note-text-updated 后，后端记录并广播 SSE。
    仅 S4/S5 有非经常性损益披露需求。

    Requirements: 9.4
    """
    valid_wp_codes = {"S4", "S5"}
    code = request.wp_code.upper()
    if code not in valid_wp_codes:
        raise HTTPException(
            400,
            f"disclosure-notify 仅支持 S4/S5（非经常性损益），"
            f"收到: {request.wp_code}",
        )

    # 从 wp_id 获取 project_id
    wp_result = await db.execute(
        sa.text(
            "SELECT wp.project_id, p.audit_year "
            "FROM working_papers wp "
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

    # 广播 disclosure:note-text-updated 到 SSE
    try:
        from app.services.event_bus import event_bus

        await event_bus.broadcast_raw(
            project_id=project_id,
            event_type="disclosure:note-text-updated",
            data={
                "wp_id": wp_id,
                "wp_code": code,
                "section": request.section,
                "text": request.text[:2000],  # 截断过长文本
                "non_recurring": True,
            },
        )
    except Exception as e:
        logger.warning("S-transaction disclosure notify failed wp=%s: %s", wp_id, e)

    return {
        "message": "披露更新通知已发布",
        "wp_code": code,
        "section": request.section,
    }
