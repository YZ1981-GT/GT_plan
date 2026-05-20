"""程序适用性裁剪路由 — PATCH trim/revert + GET summary + GET history

Sprint 1 Task 1.2: 创建 wp_procedure_trim.py 路由。
路由内部已声明完整 prefix（含 /api），注册时不加额外前缀。

Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.4, 4.1, 4.4, 6.3, 6.4, 8.1, 8.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, require_role
from app.services.procedure_trim_engine import (
    ProcedureTrimRequest,
    TrimReasonCode,
    procedure_trim_engine,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}",
    tags=["workpaper-procedure-trim"],
)


# ---------------------------------------------------------------------------
# PATCH /procedure-trim — 单行/批量裁剪 + 恢复
# ---------------------------------------------------------------------------


@router.patch("/procedure-trim")
async def patch_procedure_trim(
    project_id: str,
    wp_id: str,
    payload: ProcedureTrimRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "partner", "manager"])),
):
    """执行程序裁剪或恢复操作。

    - action=trim: 将指定行标记为 not_applicable（需 reason_code）
    - action=revert: 将指定行恢复为 pending
    """
    # Validate trim-specific requirements
    if payload.action == "trim":
        if not payload.reason_code:
            raise HTTPException(
                status_code=422,
                detail="reason_code is required for trim action",
            )
        if payload.reason_code == TrimReasonCode.OTHER:
            if not payload.reason_text or len(payload.reason_text) < 5:
                raise HTTPException(
                    status_code=422,
                    detail="reason_text must be at least 5 characters when reason_code is 'other'",
                )

    if not payload.row_ids:
        raise HTTPException(status_code=422, detail="row_ids must not be empty")

    wp_uuid = UUID(wp_id)
    project_uuid = UUID(project_id)

    if payload.action == "trim":
        result = await procedure_trim_engine.trim(
            db=db,
            wp_id=wp_uuid,
            sheet_key=payload.sheet_key,
            row_ids=payload.row_ids,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
            user_id=current_user.id,
            project_id=project_uuid,
        )
    else:
        result = await procedure_trim_engine.revert(
            db=db,
            wp_id=wp_uuid,
            sheet_key=payload.sheet_key,
            row_ids=payload.row_ids,
            user_id=current_user.id,
            project_id=project_uuid,
        )

    await db.commit()
    return result.to_response().model_dump()


# ---------------------------------------------------------------------------
# GET /procedure-trim/summary — 裁剪汇总
# ---------------------------------------------------------------------------


@router.get("/procedure-trim/summary")
async def get_procedure_trim_summary(
    project_id: str,
    wp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取裁剪汇总统计（所有角色可见）。"""
    wp_uuid = UUID(wp_id)
    summary = await procedure_trim_engine.get_summary(db=db, wp_id=wp_uuid)
    return summary.to_response().model_dump()


# ---------------------------------------------------------------------------
# GET /procedure-trim/history — 操作历史
# ---------------------------------------------------------------------------


@router.get("/procedure-trim/history")
async def get_procedure_trim_history(
    project_id: str,
    wp_id: str,
    user_id: str | None = None,
    reason_code: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取裁剪操作历史（所有角色可见）。

    支持按操作人/理由/时间范围筛选。
    """
    wp_uuid = UUID(wp_id)
    filters: dict = {}
    if user_id:
        filters["user_id"] = user_id
    if reason_code:
        filters["reason_code"] = reason_code
    if start_time:
        filters["start_time"] = start_time
    if end_time:
        filters["end_time"] = end_time

    entries = await procedure_trim_engine.get_history(
        db=db, wp_id=wp_uuid, filters=filters if filters else None
    )
    return [e.model_dump() for e in entries]
