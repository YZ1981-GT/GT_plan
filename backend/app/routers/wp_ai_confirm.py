"""底稿 AI 内容确认路由 — R3 Sprint 4 Task 22

PATCH  /api/projects/{project_id}/workpapers/{wp_id}/ai-confirm
  body: {cell_ref: str, action: 'accept'|'reject'|'revise', revised_value?: str}

确认/拒绝/修订底稿中 AI 生成的内容单元格。
更新 parsed_data 中对应 cell 的 confirmed_by / confirmed_at 字段。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}",
    tags=["底稿AI确认"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AiConfirmRequest(BaseModel):
    """AI 内容确认请求体"""

    cell_ref: str = Field(..., description="单元格引用，如 'B2' 或 'ai_analysis'")
    action: Literal["accept", "reject", "revise"] = Field(
        ..., description="操作类型: accept=采纳, reject=拒绝, revise=修订"
    )
    revised_value: Optional[str] = Field(
        None, description="修订后的值（仅 action='revise' 时需要）"
    )


class AiConfirmResponse(BaseModel):
    """AI 内容确认响应"""

    cell_ref: str
    action: str
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.patch("/ai-confirm")
async def confirm_ai_content(
    project_id: UUID,
    wp_id: UUID,
    body: AiConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiConfirmResponse:
    """确认/拒绝/修订底稿中的 AI 生成内容。

    - accept: 标记 confirmed_by + confirmed_at，保留原值
    - reject: 标记 confirmed_by + confirmed_at + action='rejected'，
              将 cell type 改为 'ai_rejected'
    - revise: 标记 confirmed_by + confirmed_at，替换 value 为 revised_value
    """
    from app.models.workpaper_models import WorkingPaper

    # 查询底稿
    stmt = select(WorkingPaper).where(
        WorkingPaper.id == wp_id,
        WorkingPaper.project_id == project_id,
    )
    # 兼容 SoftDeleteMixin
    if hasattr(WorkingPaper, "is_deleted"):
        stmt = stmt.where(WorkingPaper.is_deleted == False)  # noqa: E712

    result = await db.execute(stmt)
    wp = result.scalar_one_or_none()

    if not wp:
        raise HTTPException(status_code=404, detail="底稿不存在")

    parsed_data = wp.parsed_data or {}
    cell_ref = body.cell_ref
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(current_user.id)

    # 查找并更新对应的 AI 内容节点
    updated = _update_ai_cell(parsed_data, cell_ref, body.action, user_id, now, body.revised_value)

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"未找到 cell_ref='{cell_ref}' 对应的 AI 生成内容",
        )

    # 持久化
    wp.parsed_data = parsed_data
    # 标记 JSONB 字段已修改（SQLAlchemy 需要显式标记）
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(wp, "parsed_data")
    await db.flush()
    await db.commit()

    action_labels = {"accept": "采纳", "reject": "拒绝", "revise": "修订"}
    return AiConfirmResponse(
        cell_ref=cell_ref,
        action=body.action,
        confirmed_by=user_id,
        confirmed_at=now,
        message=f"AI 内容已{action_labels[body.action]}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _update_ai_cell(
    parsed_data: dict,
    cell_ref: str,
    action: str,
    user_id: str,
    now: str,
    revised_value: Optional[str] = None,
) -> bool:
    """在 parsed_data 中查找 cell_ref 对应的 AI 内容节点并更新。

    支持两种结构：
    1. parsed_data.cells 列表中按 row+col 匹配（cell_ref 格式如 "B2"）
    2. parsed_data 顶层字段名匹配（cell_ref 格式如 "ai_analysis"）

    Returns:
        True 如果找到并更新了节点，False 如果未找到。
    """
    # 策略 1: 检查顶层字段
    if cell_ref in parsed_data:
        node = parsed_data[cell_ref]
        if isinstance(node, dict) and node.get("type") == "ai_generated":
            _apply_action(node, action, user_id, now, revised_value)
            return True

    # 策略 2: 检查 cells 列表
    cells = parsed_data.get("cells", [])
    if isinstance(cells, list):
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            if cell.get("type") != "ai_generated":
                continue
            # 匹配 cell_ref: 支持 "B2" 格式（col+row）或直接 cell_ref 字段
            cell_id = cell.get("cell_ref") or _build_cell_ref(cell)
            if cell_id == cell_ref:
                _apply_action(cell, action, user_id, now, revised_value)
                return True

    # 策略 3: 递归搜索嵌套结构
    return _recursive_find_and_update(parsed_data, cell_ref, action, user_id, now, revised_value)


def _build_cell_ref(cell: dict) -> str:
    """从 cell dict 构建 cell_ref 字符串（如 'B2'）。"""
    col = cell.get("col", "")
    row = cell.get("row", "")
    return f"{col}{row}"


def _apply_action(
    node: dict,
    action: str,
    user_id: str,
    now: str,
    revised_value: Optional[str] = None,
) -> None:
    """对 AI 内容节点应用确认操作。"""
    node["confirmed_by"] = user_id
    node["confirmed_at"] = now

    if action == "accept":
        node["confirm_action"] = "accepted"
    elif action == "reject":
        node["confirm_action"] = "rejected"
        node["type"] = "ai_rejected"
    elif action == "revise":
        node["confirm_action"] = "revised"
        if revised_value is not None:
            node["original_value"] = node.get("value")
            node["value"] = revised_value


def _recursive_find_and_update(
    data: dict,
    cell_ref: str,
    action: str,
    user_id: str,
    now: str,
    revised_value: Optional[str] = None,
) -> bool:
    """递归搜索嵌套结构中的 AI 内容节点。"""
    for key, value in data.items():
        if isinstance(value, dict):
            if value.get("type") == "ai_generated":
                ref = value.get("cell_ref") or key
                if ref == cell_ref:
                    _apply_action(value, action, user_id, now, revised_value)
                    return True
            # 递归
            if _recursive_find_and_update(value, cell_ref, action, user_id, now, revised_value):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if item.get("type") == "ai_generated":
                        ref = item.get("cell_ref") or _build_cell_ref(item)
                        if ref == cell_ref:
                            _apply_action(item, action, user_id, now, revised_value)
                            return True
                    if _recursive_find_and_update(item, cell_ref, action, user_id, now, revised_value):
                        return True
    return False
