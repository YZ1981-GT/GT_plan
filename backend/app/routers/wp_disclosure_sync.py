"""C 类底稿 → disclosure_notes 模块单向同步端点

POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper

按 design §12.1 推荐选项 A：底稿是编辑入口，单向 push 到附注模块。
disclosure_notes 模块继续保留独立编辑器（向后兼容），并在前端展示
"此数据由底稿同步" banner。

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.wp_disclosure_sync_service import sync_from_workpaper

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects",
    tags=["wp-disclosure-sync"],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SyncFromWorkpaperRequest(BaseModel):
    """C 类底稿 → disclosure_notes 同步请求体"""

    wp_id: UUID = Field(..., description="源底稿 ID")
    sheet_name: str = Field(..., min_length=1, description="C 类附注 sheet 名")
    section_id: str = Field(
        ...,
        min_length=1,
        description='附注 section（如 "五-1-1 应收账款"）',
    )
    sub_table_data: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="子表数据：sub_table_id → 行列表",
    )
    current_standard: str = Field(
        ...,
        min_length=1,
        description='当前准则（如 "soe_standalone" / "listed_standalone"）',
    )
    year: int | None = Field(
        None,
        description="审计年度（可选；不传时取当前年）",
    )


class SyncFromWorkpaperResponse(BaseModel):
    """同步结果"""

    success: bool
    section_id: str
    synced_at: str
    rows_synced: int
    created: bool = Field(
        ...,
        description="是否新建了 disclosure_notes 记录（False=更新现有）",
    )


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post(
    "/{project_id}/disclosure-notes/sync-from-workpaper",
    response_model=SyncFromWorkpaperResponse,
)
async def sync_disclosure_from_workpaper(
    project_id: UUID,
    body: SyncFromWorkpaperRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("edit")),
) -> SyncFromWorkpaperResponse:
    """C 类附注 sheet 保存触发的单向同步端点。

    EARS:
    - WHEN 用户在 C 类 sheet 保存附注披露数据 THEN 系统 SHALL 自动 push 到
      disclosure_notes 模块对应 section
    - WHEN disclosure_notes 模块直接编辑 THEN 系统 SHALL 仅更新 disclosure_notes 表，
      不反向写回 C 类 sheet
    """
    try:
        result = await sync_from_workpaper(
            db,
            project_id,
            wp_id=body.wp_id,
            sheet_name=body.sheet_name,
            section_id=body.section_id,
            sub_table_data=body.sub_table_data,
            current_standard=body.current_standard,
            user=current_user,
            year=body.year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "sync_disclosure_from_workpaper failed: project=%s wp_id=%s section=%s",
            project_id, body.wp_id, body.section_id,
        )
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"附注同步失败: {exc}",
        ) from exc

    return SyncFromWorkpaperResponse(**result)
