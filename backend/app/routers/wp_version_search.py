"""底稿历史版本搜索路由 — proposal-remaining-18 task 5.4 (S-4)

GET /api/working-papers/{wp_id}/versions/search?q=keyword
  → 在底稿全部历史版本的 parsed_data.cells / snapshot_data 中模糊搜索，返回匹配
    的 cell 列表（含 version_id, sheet, cell_ref, value, snapshot_at）。

注册到 router_registry.workpaper 域 §119。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_version_search_service import search_versions

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/working-papers",
    tags=["wp-version-search"],
)


@router.get("/{wp_id}/versions/search")
async def search_workpaper_versions(
    wp_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500, description="返回结果上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """历史版本搜索 — 在快照 + 当前 parsed_data 中模糊匹配关键词

    返回示例::

        {
          "wp_id": "...",
          "query": "应收账款",
          "total": 3,
          "results": [
            {
              "version_id": "<uuid>",
              "trigger_event": "sign",
              "snapshot_at": "2026-05-15T10:00:00",
              "sheet": "Sheet1",
              "cell_ref": "B12",
              "value": "应收账款余额 1234.56",
              "field": "formula_value"
            }
          ]
        }
    """
    try:
        results = await search_versions(db, wp_id, q, limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("version search failed wp=%s err=%s", wp_id, e)
        results = []

    return {
        "wp_id": str(wp_id),
        "query": q,
        "total": len(results),
        "results": results,
    }
