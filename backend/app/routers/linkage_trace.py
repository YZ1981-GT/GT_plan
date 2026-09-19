"""P1-1.5: 统一穿透查询 API

GET /api/projects/{project_id}/linkage/trace
参数: source_type, source_id, cell(可选), year(可选)
返回: LinkageContract 列表
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.linkage_facade_service import LinkageFacadeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/linkage",
    tags=["linkage"],
)


@router.get("/trace")
async def get_linkage_trace(
    project_id: UUID,
    source_type: str = Query(..., description="来源类型: trial_balance/workpaper/note/report"),
    source_id: str = Query(..., description="来源对象 ID"),
    cell: Optional[str] = Query(None, description="来源单元格或字段"),
    year: Optional[int] = Query(None, description="年度"),
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
):
    """统一穿透查询 — 返回 LinkageContract 列表。

    根据 source_type 和 source_id 查询所有联动关系，
    包含 conflict/stale 状态和跳转路由。
    """
    facade = LinkageFacadeService(db)
    contracts = await facade.trace(
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        cell=cell,
        year=year,
    )
    return {"contracts": contracts, "total": len(contracts)}
