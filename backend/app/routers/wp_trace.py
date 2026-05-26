"""底稿溯源端点

GET /api/workpapers/trace
按 design §5.1.7 实现：报表/附注/底稿溯源链路双路查询。

Requirements: 3.11.6（报表附注溯源链路）
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.services.wp_trace_service import (
    trace_downstream,
    trace_upstream,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers",
    tags=["wp-trace"],
)


# ─── Response schemas ────────────────────────────────────────────────────────


class TraceItemResponse(BaseModel):
    wp_code: str
    sheet: str | None = None
    cell: str | None = None
    value: Any = None
    label: str | None = None
    target_type: str | None = None
    target_identifier: str | None = None


class TraceResponse(BaseModel):
    source: str
    identifier: str
    direction: str
    items: list[TraceItemResponse]


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("/trace", response_model=TraceResponse)
async def trace_workpaper(
    source: str = Query(..., description="溯源源类型：report / disclosure / workpaper"),
    identifier: str = Query(..., description="溯源对象标识：row_code / section_id / wp_code[:sheet[:cell]]"),
    direction: str = Query(..., description="溯源方向：upstream（反向）/ downstream（正向）"),
    project_id: UUID = Query(..., description="项目 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """报表/附注/底稿溯源端点。

    EARS:
    - WHEN direction=upstream THEN 返回喂入此对象的上游单元格列表
    - WHEN direction=downstream THEN 返回引用此对象的下游对象列表
    - IF source=report AND direction=downstream THEN items=[] (报表是终点)
    - IF source=disclosure AND direction=downstream THEN items=[] (附注是终点)
    - IF 项目数据不足或对应记录缺失 THEN 返回 items=[] (best-effort 不报错)
    """
    # ─── 校验参数 ───
    if source not in ("report", "disclosure", "workpaper"):
        raise HTTPException(
            status_code=422,
            detail=f"非法 source 值: {source}（应为 report / disclosure / workpaper）",
        )
    if direction not in ("upstream", "downstream"):
        raise HTTPException(
            status_code=422,
            detail=f"非法 direction 值: {direction}（应为 upstream / downstream）",
        )

    cleaned_identifier = identifier.strip()
    if not cleaned_identifier:
        raise HTTPException(status_code=422, detail="identifier 不能为空")

    # ─── 分发 ───
    try:
        if direction == "upstream":
            result = await trace_upstream(
                db=db,
                project_id=project_id,
                source=source,
                identifier=cleaned_identifier,
            )
        else:
            result = await trace_downstream(
                db=db,
                project_id=project_id,
                source=source,
                identifier=cleaned_identifier,
            )
    except Exception as exc:
        logger.exception(
            "Trace failed: source=%s, identifier=%s, direction=%s, project=%s",
            source, cleaned_identifier, direction, project_id,
        )
        # best-effort：异常时返回空列表而非 500
        return TraceResponse(
            source=source,
            identifier=cleaned_identifier,
            direction=direction,
            items=[],
        )

    return TraceResponse(**result.to_dict())
