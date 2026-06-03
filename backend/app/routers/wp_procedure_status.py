"""程序状态 + 程序分类持久化端点（E1 Sprint 2 Task 2.13/2.40）

锚定 requirements:
- F3.1 程序完成状态三档（filled→reviewed→approved）
- F1.8 程序分类用户勾选驱动 sheet 显隐

端点：
- PATCH /api/projects/{pid}/working-papers/{wp_id}/procedure-status
- PUT /api/workpapers/{wp_id}/procedure-categories
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db


router = APIRouter(
    prefix="/api/projects/{project_id}/working-papers",
    tags=["workpaper-procedure-status"],
)

# 独立 router 用于 procedure-categories（路径不在项目下）
categories_router = APIRouter(
    prefix="/api/workpapers",
    tags=["workpaper-procedure-categories"],
)


class ProcedureStatusUpdate(BaseModel):
    sheet_key: str = Field(..., description="如 e1a / e26a")
    row: str = Field(..., description="行号，如 R17")
    status: str = Field(..., description="pending/filled/reviewed/approved/not_applicable")
    category: str | None = None
    assertions: list[str] | None = None
    workpaper_refs: list[str] | None = None
    description: str | None = None


_VALID_STATUS = {"pending", "filled", "reviewed", "approved", "not_applicable"}


@router.patch("/{wp_id}/procedure-status")
async def update_procedure_status(
    project_id: str,
    wp_id: str,
    payload: ProcedureStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新程序行状态（filled→reviewed→approved 三档晋级）。"""
    if payload.status not in _VALID_STATUS:
        raise HTTPException(400, f"invalid status: {payload.status}")

    from app.models.workpaper_models import WorkingPaper

    wp_uuid = UUID(wp_id)
    result = await db.execute(select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(404, "workpaper not found")

    parsed: dict[str, Any] = dict(wp.parsed_data or {})
    procedure_status: dict[str, Any] = dict(parsed.get("procedure_status") or {})
    sheet_data: dict[str, Any] = dict(procedure_status.get(payload.sheet_key) or {})
    row_data: dict[str, Any] = dict(sheet_data.get(payload.row) or {})

    now_iso = datetime.now(timezone.utc).isoformat()
    row_data["status"] = payload.status
    if payload.category is not None:
        row_data["category"] = payload.category
    if payload.assertions is not None:
        row_data["assertions"] = payload.assertions
    if payload.workpaper_refs is not None:
        row_data["workpaper_refs"] = payload.workpaper_refs
    if payload.description is not None:
        row_data["description"] = payload.description

    # 时间戳：filled/reviewed/approved 各自记录
    if payload.status == "filled":
        row_data["filled_at"] = now_iso
        row_data["filled_by"] = str(current_user.id)
    elif payload.status == "reviewed":
        row_data["reviewed_at"] = now_iso
        row_data["reviewed_by"] = str(current_user.id)
    elif payload.status == "approved":
        row_data["approved_at"] = now_iso
        row_data["approved_by"] = str(current_user.id)

    sheet_data[payload.row] = row_data
    procedure_status[payload.sheet_key] = sheet_data
    parsed["procedure_status"] = procedure_status
    wp.parsed_data = parsed
    # SQLAlchemy JSONB 需要显式标记为已修改
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(wp, "parsed_data")
    await db.commit()
    try:
        from app.services.wp_parsed_data_service import touch_wp_registry

        await touch_wp_registry(wp.project_id)
    except Exception as touch_err:
        import logging

        logging.getLogger(__name__).warning(
            "touch_wp_registry after procedure_status: %s", touch_err
        )

    return {
        "ok": True,
        "wp_id": wp_id,
        "sheet_key": payload.sheet_key,
        "row": payload.row,
        "status": payload.status,
    }


class ProcedureCategoriesUpdate(BaseModel):
    procedure_categories: list[str] = Field(default_factory=list)


_VALID_CATEGORIES = {"常规★", "备选", "IPO 应对", "IPO应对"}


@categories_router.put("/{wp_id}/procedure-categories")
async def update_procedure_categories(
    wp_id: str,
    payload: ProcedureCategoriesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """持久化用户勾选的程序分类（F1.8）。

    联动逻辑：勾选"IPO 应对" → 联动 LinkageBus 加载 F4 文件
    （由前端订阅 procedure-categories:changed 事件触发刷新）。
    """
    # 校验
    cats = [c for c in (payload.procedure_categories or []) if c in _VALID_CATEGORIES]
    if not cats:
        cats = ["常规★"]  # 默认至少包含常规

    from app.models.workpaper_models import WorkingPaper

    wp_uuid = UUID(wp_id)
    result = await db.execute(select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(404, "workpaper not found")

    parsed = dict(wp.parsed_data or {})
    parsed["procedure_categories"] = cats
    wp.parsed_data = parsed
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(wp, "parsed_data")
    await db.commit()
    try:
        from app.services.wp_parsed_data_service import touch_wp_registry

        await touch_wp_registry(wp.project_id)
    except Exception as touch_err:
        import logging

        logging.getLogger(__name__).warning(
            "touch_wp_registry after procedure_categories: %s", touch_err
        )

    return {
        "ok": True,
        "wp_id": wp_id,
        "procedure_categories": cats,
    }


@categories_router.get("/{wp_id}/procedure-categories")
async def get_procedure_categories(
    wp_id: str,
    db: AsyncSession = Depends(get_db),
):
    """读取当前勾选的程序分类。"""
    from app.models.workpaper_models import WorkingPaper

    wp_uuid = UUID(wp_id)
    result = await db.execute(select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(404, "workpaper not found")
    parsed = wp.parsed_data or {}
    cats = parsed.get("procedure_categories") or ["常规★"]
    return {"wp_id": wp_id, "procedure_categories": cats}
