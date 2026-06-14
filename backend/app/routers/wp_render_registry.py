"""底稿类型注册表 API 路由

GET /api/workpapers/render-registry — 返回完整注册表
GET /api/workpapers/render-registry/{wp_code} — 单条查找
GET /api/workpapers/header-data — 返回底稿表头字段映射
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import workpaper_render_registry_service as registry
from app.services.wp_header_data_service import get_header_data

router = APIRouter(prefix="/api/workpapers/render-registry")


@router.get("")
async def get_render_registry() -> dict[str, Any]:
    """返回完整注册表（含 render_types + entries）"""
    return {
        "render_types": registry.get_render_types(),
        "entries": registry.get_all_entries(),
    }


@router.get("/{wp_code}")
async def get_registry_entry(wp_code: str) -> dict[str, Any]:
    """查找单个 wp_code 的注册信息"""
    entry = registry.lookup(wp_code)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"未知底稿编码: {wp_code}")
    return {"wp_code": wp_code, **entry}


# ─── 表头数据端点（与注册表同 prefix 避免路由冲突） ────────────────────

from fastapi import APIRouter as _R  # noqa: E402

header_router = _R(prefix="/api/workpapers/header-data")


@header_router.get("")
async def get_wp_header_data(
    project_id: UUID = Query(...),
    wp_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回底稿表头字段映射（纯数据，不写文件）"""
    return await get_header_data(db, project_id, wp_code)
