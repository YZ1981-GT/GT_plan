"""程序表行级访问（spec procedure-trim-generation-delegation-chain 需求 7.4）。

``GET /api/workpapers/{wp_id}/program-row-access?sheet_name=``：当前用户在这张程序表上能改哪些行、能否裁剪、
各行执行人。前端据此把非本人行置为只读并显示执行人；服务端保存时用同一判定合并（``program_row_guard``）。
挂在底稿组，路由级可见性门（``dedicated_wp_gate``，与其余 ``/{wp_id}/...`` 端点同一口径）先判定能否看到这张底稿，
看不到统一 404。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.wp_visibility.program_row_guard import resolve_row_access

router = APIRouter(prefix="/api/workpapers", tags=["wp-program-row-access"])


@router.get("/{wp_id}/program-row-access")
async def get_program_row_access(
    wp_id: UUID,
    sheet_name: str = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    wp = (await db.execute(sa.select(WorkingPaper).where(
        WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return (await resolve_row_access(db, current_user, wp, sheet_name)).to_dict()
