"""四张抵销后表 canonical projection 只读路由（consolidation-run-and-workpaper-lifecycle-closure 批 3）。

GET /api/consolidation/post-elimination/{project_id}/{year}
  返回抵消后长投 / 抵消后投资收益 / 少数股东权益损益 / 资本公积抵销列的权威抵销金额与逐企业分解。

路由段以 ``post-elimination`` 开头（不是 ``{project_id}`` 开头），避免与同前缀下其它合并路由互相遮蔽。
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.deps import require_project_access
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/consolidation/post-elimination",
    tags=["合并抵销后投影"],
)


@router.get("/{project_id}/{year}")
async def get_post_elimination_projection(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """四张抵销后表的只读 canonical projection（自动列来自 approved 分录，manual override 原样带出）。"""
    from app.services.consol_post_elimination_projection import (
        load_post_elimination_projection,
        projection_to_dict,
    )

    try:
        projection = await load_post_elimination_projection(db, project_id, year)
    except Exception as exc:  # noqa: BLE001 — 口径装载异常转 4xx，不暴露内部栈
        logger.warning("抵销后投影装载失败：项目=%s 年度=%s：%s", project_id, year, exc)
        raise HTTPException(status_code=400, detail=f"抵销后投影装载失败：{exc}") from exc
    if projection is None:
        raise HTTPException(status_code=400, detail="项目不是合并项目，或无法构建企业树")
    return projection_to_dict(projection)
