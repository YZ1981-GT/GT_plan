"""底稿 HTML 数据保存端点

POST /api/workpapers/{wp_id}/save
按 design §5.1.2 实现：保存 HTML 数据到 parsed_data['html_data']。

Requirements: 2.2 原则 4（决策可追踪）+ 3.11.4（跨底稿引用传播）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.cross_ref_service import cross_ref_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-html-save"],
)


# ─── Request / Response schemas ──────────────────────────────────────────────


class SaveHtmlDataRequest(BaseModel):
    """保存 HTML 数据请求体"""
    sheet_name: str = Field(..., description="Sheet 名称")
    html_data: dict = Field(..., description="HTML 渲染数据")
    schema_version: str = Field(..., description="Schema 版本号（如 v2025-R5）")
    changed_cells: list[str] | None = Field(
        None, description="变更的 cell 列表（可选，用于优化跨底稿引用检测）"
    )


class StaleImpactItem(BaseModel):
    """受影响的跨底稿引用"""
    ref_id: str
    target_wp_code: str
    target_sheet: str | None = None
    target_cell: str | None = None


class SaveHtmlDataResponse(BaseModel):
    """保存成功响应"""
    saved_at: str
    stale_impact: list[StaleImpactItem] = []


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/{wp_id}/save")
async def save_html_data(
    wp_id: UUID,
    body: SaveHtmlDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SaveHtmlDataResponse:
    """保存 HTML 数据到 parsed_data['html_data'][sheet_name]。

    EARS:
    - WHEN 保存成功 AND 存在 cross_wp_references 引用此 cell
      THEN 系统 SHALL 发布 SSE cross_ref.updated
    - WHEN schema_version 与服务端 current 不一致 THEN 返回 409
    - IF html_data 校验失败 THEN 返回 422 + 字段级错误
    """
    # ─── Step 1: 查 working_paper ─────────────────────────────────────────
    wp_query = sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.is_deleted == False,  # noqa: E712
    )
    wp_result = await db.execute(wp_query)
    working_paper = wp_result.scalars().first()

    if working_paper is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # ─── Step 2: schema_version 冲突检测 ──────────────────────────────────
    parsed_data = working_paper.parsed_data or {}
    current_schema_version = parsed_data.get("schema_version")

    # 如果服务端已有 schema_version 且与请求不一致，返回 409
    if (
        current_schema_version is not None
        and current_schema_version != body.schema_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "schema_version_conflict",
                "message": (
                    f"Schema 版本冲突：服务端当前版本为 {current_schema_version}，"
                    f"请求版本为 {body.schema_version}。请刷新后重试。"
                ),
                "server_version": current_schema_version,
                "client_version": body.schema_version,
            },
        )

    # ─── Step 3: JSON Schema 基础校验 ─────────────────────────────────────
    # 校验 html_data 必须是 dict 且 sheet_name 非空
    if not isinstance(body.html_data, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "html_data 必须是 JSON 对象",
                "field": "html_data",
            },
        )

    if not body.sheet_name.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error": "validation_error",
                "message": "sheet_name 不能为空",
                "field": "sheet_name",
            },
        )

    # ─── Step 4: 获取 wp_code（用于跨底稿引用检测）────────────────────────
    wp_code = await cross_ref_service.get_wp_code_for_wp_id(wp_id, db)

    # ─── Step 5: 保存前获取旧数据（用于变更检测）──────────────────────────
    html_data_all = parsed_data.get("html_data", {})
    old_sheet_data = html_data_all.get(body.sheet_name)

    # ─── Step 6: Merge html_data 到 parsed_data['html_data'][sheet_name] ──
    if "html_data" not in parsed_data:
        parsed_data["html_data"] = {}

    parsed_data["html_data"][body.sheet_name] = body.html_data

    # 更新元数据
    now = datetime.now(timezone.utc)
    parsed_data["schema_version"] = body.schema_version
    parsed_data["last_modified_by"] = str(current_user.id)
    parsed_data["last_modified_at"] = now.isoformat()

    # 记录变更的 sheets
    changed_sheets = parsed_data.get("changed_sheets_last_save", [])
    if body.sheet_name not in changed_sheets:
        changed_sheets.append(body.sheet_name)
    parsed_data["changed_sheets_last_save"] = changed_sheets

    # ─── Step 7: 写入数据库 ───────────────────────────────────────────────
    await db.execute(
        sa.update(WorkingPaper)
        .where(WorkingPaper.id == wp_id)
        .values(
            parsed_data=parsed_data,
            updated_by=current_user.id,
            updated_at=now,
        )
    )
    await db.commit()

    # ─── Step 8: 跨底稿引用变更检测 ──────────────────────────────────────
    stale_impact: list[StaleImpactItem] = []

    if wp_code:
        changes = cross_ref_service.detect_changes(
            wp_code=wp_code,
            sheet_name=body.sheet_name,
            old_html_data=old_sheet_data,
            new_html_data=body.html_data,
            changed_cells=body.changed_cells,
        )

        if changes:
            stale_impact = [
                StaleImpactItem(
                    ref_id=c.ref_id,
                    target_wp_code=c.target_wp_code,
                    target_sheet=c.target_sheet,
                    target_cell=c.target_cell,
                )
                for c in changes
            ]

            # 发布 SSE cross_ref.updated 事件
            _publish_cross_ref_updated(
                project_id=working_paper.project_id,
                source_wp_code=wp_code,
                changed_sheets=[body.sheet_name],
                affected_targets=[c.target_wp_code for c in changes],
            )

    return SaveHtmlDataResponse(
        saved_at=now.isoformat(),
        stale_impact=stale_impact,
    )


# ─── SSE 发布辅助 ────────────────────────────────────────────────────────────


def _publish_cross_ref_updated(
    project_id: UUID,
    source_wp_code: str,
    changed_sheets: list[str],
    affected_targets: list[str],
) -> None:
    """发布 cross_ref.updated SSE 事件。

    使用 EventBus.broadcast_raw 轻量级广播（不走完整 dispatch），
    写入 Redis Stream 供 SSE 端订阅。
    """
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            event_type="cross_ref.updated",
            extra={
                "project_id": str(project_id),
                "source_wp_code": source_wp_code,
                "changed_sheets": changed_sheets,
                "affected_targets": list(set(affected_targets)),
            },
        )
        logger.info(
            "Published cross_ref.updated: source=%s, targets=%s",
            source_wp_code,
            list(set(affected_targets)),
        )
    except Exception as exc:
        # SSE 发布失败不应阻断保存流程
        logger.warning("Failed to publish cross_ref.updated SSE: %s", exc)
