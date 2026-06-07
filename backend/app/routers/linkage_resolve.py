"""P0-3: 路由解析 API

POST /api/projects/{project_id}/linkage/resolve-route
支持 workpaper (wp_id/wp_code), report (row_code), note (section/table/cell)
"""
from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access
from app.models.core import User
from app.models.workpaper_models import WpIndex
from app.schemas.linkage_contract import (
    ResolveRouteRequest,
    ResolveRouteResponse,
    TargetType,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/linkage",
    tags=["linkage"],
)

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


async def _resolve_wp_id(db: AsyncSession, project_id: UUID, target_id: str) -> str | None:
    """将 wp_code 解析为 working_paper_id，UUID 直接返回。"""
    if _UUID_PATTERN.match(target_id):
        return target_id

    # wp_code 查 wp_index 表
    stmt = select(WpIndex).where(
        WpIndex.project_id == project_id,
        WpIndex.wp_code == target_id,
    )
    result = await db.execute(stmt)
    wp_idx = result.scalar_one_or_none()
    if wp_idx and wp_idx.working_paper_id:
        return str(wp_idx.working_paper_id)
    return None


@router.post("/resolve-route", response_model=ResolveRouteResponse)
async def resolve_route(
    project_id: UUID,
    body: ResolveRouteRequest,
    current_user: User = Depends(require_project_access("readonly")),
    db: AsyncSession = Depends(get_db),
) -> ResolveRouteResponse:
    """解析 LinkageContract 目标为可跳转前端路由。

    支持的 target_type:
    - workpaper: 接受 wp_id (UUID) 或 wp_code (如 D1)，解析后返回底稿编辑器路由
    - report: 返回报表页路由并定位到 row_code
    - note: 返回附注编辑器路由并定位 section/table/cell
    - trial_balance: 返回试算表页并高亮行
    """
    pid = str(project_id)
    target_type = body.target_type
    target_id = body.target_id
    target_cell = body.target_cell

    if target_type == TargetType.workpaper:
        wp_id = await _resolve_wp_id(db, project_id, target_id)
        if wp_id:
            route = f"/projects/{pid}/workpapers/{wp_id}"
            return ResolveRouteResponse(route=route, resolved_id=wp_id)
        return ResolveRouteResponse(
            route=None,
            error=f"无法解析底稿：{target_id}（wp_code 不存在或未关联底稿）",
        )

    if target_type == TargetType.report:
        route = f"/projects/{pid}/reports?highlight={target_id}"
        return ResolveRouteResponse(route=route, resolved_id=target_id)

    if target_type == TargetType.note:
        route = f"/projects/{pid}/disclosure-notes?section={target_id}"
        if target_cell:
            route += f"&cell={target_cell}"
        return ResolveRouteResponse(route=route, resolved_id=target_id)

    if target_type == TargetType.trial_balance:
        route = f"/projects/{pid}/trial-balance?highlight={target_id}"
        return ResolveRouteResponse(route=route, resolved_id=target_id)

    if target_type == TargetType.adjustment:
        route = f"/projects/{pid}/adjustments?highlight={target_id}"
        return ResolveRouteResponse(route=route, resolved_id=target_id)

    if target_type == TargetType.ledger:
        route = f"/projects/{pid}/ledger?account={target_id}"
        return ResolveRouteResponse(route=route, resolved_id=target_id)

    # 不支持的 target_type（attachment / ai 等暂不支持路由跳转）
    return ResolveRouteResponse(
        route=None,
        error=f"目标类型 {target_type.value} 暂不支持路由解析",
    )
