"""S34 核查事项清单 API — 返回 S34ChecklistItem[] 含法规溯源/适用性/完成状态.

端点：
- GET /api/projects/{project_id}/s34-checklist  → List[S34ChecklistItem]

数据源：静态 regRef 映射 + wp_index 动态适用性/状态。
注册到 router_registry/workpaper.py 数据组。

Requirements: 3.2, 9.1, 12.1
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.s34_checklist_service import get_s34_checklist

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects",
    tags=["S34 核查清单"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class RegRef(BaseModel):
    """法规溯源引用"""
    csrc: Optional[str] = Field(None, description="证监会发行类条目")
    sse: Optional[str] = Field(None, description="上交所指南条目")
    szse: Optional[str] = Field(None, description="深交所指南条目")
    bse: Optional[str] = Field(None, description="北交所指引条目")
    title: str = Field(description="核查事项名称")


class S34ChecklistItem(BaseModel):
    """S34 核查事项清单条目"""
    seq: int = Field(description="序号")
    wp_code: str = Field(description="底稿编码 (S34-1 ~ S34-41)")
    name: str = Field(description="核查事项名称")
    reg_ref: RegRef = Field(description="法规溯源")
    applicability: str = Field(description="适用性: applicable / not_applicable / unknown")
    status: str = Field(description="完成状态: completed / in_progress / not_started")


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/s34-checklist", response_model=list[S34ChecklistItem])
async def get_project_s34_checklist(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """返回 S34 核查事项清单 — 41 条专项底稿的法规溯源 + 适用性 + 完成状态.

    适用性判断：wp_index 中存在该 wp_code 底稿 → applicable，否则 → not_applicable。
    完成状态：基于 wp_index.status 映射（draft_complete/review_passed/archived → completed）。

    Requirements: 3.2, 9.1, 12.1
    """
    try:
        checklist = await get_s34_checklist(project_id, db)
    except Exception as e:
        logger.error("S34 checklist query failed project=%s: %s", project_id, e)
        raise HTTPException(500, "S34 核查清单获取失败")

    return checklist
