"""合并 readiness 七域五态只读路由（批 5）。"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/consolidation/readiness",
    tags=["合并就绪度"],
)


@router.get("/{project_id}/{year}")
async def get_consol_readiness(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_project_access("readonly")),
):
    """七域五态 readiness：事实与阻断分离，不执行重算。"""
    from app.services.consol_readiness_service import load_consol_readiness

    try:
        return await load_consol_readiness(db, project_id, year)
    except Exception as exc:
        logger.warning("readiness 装载失败：%s", exc)
        raise HTTPException(status_code=400, detail=f"合并就绪度读取失败：{exc}") from exc
