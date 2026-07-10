"""底稿类型注册表 API 路由

GET /api/workpapers/render-registry — 返回完整注册表
GET /api/workpapers/render-registry/{wp_code} — 转发至 ACNR resolve 统一出口（R13.2）
GET /api/workpapers/header-data — 返回底稿表头字段映射

M1: render-registry/{wp_code} 转发至 ACNR resolve（R13.2, R13.4, R13.5）。
转发失败返回错误，不回退旧逻辑。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services import workpaper_render_registry_service as registry
from app.services.wp_header_data_service import get_header_data

logger = logging.getLogger(__name__)

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
    """查找单个 wp_code 的注册信息 — 转发至 ACNR resolve 统一出口。

    M1 转发逻辑（R13.2, R13.4, R13.5）：
    - 先通过 ACNR resolve 获取 addr_id + 元数据
    - 合并 render_registry 原有 component_type 等注册信息
    - 一次查询返回 exists / trimmed / reason（R13.4）
    - 转发失败返回错误，不回退旧逻辑（R13.5）
    """
    from app.services.acnr.resolver import full_resolve

    try:
        # 通过 ACNR resolve 解析 wp_code
        resolve_result = await full_resolve(
            index_ref=f"wp:{wp_code}",
            db=None,
        )

        # 从 render_registry 获取 component_type 等原有注册信息
        entry = registry.lookup(wp_code)

        # 构建统一响应（R13.4: 一次查询返回 exists/trimmed/reason）
        response: dict[str, Any] = {
            "wp_code": wp_code,
            "exists": resolve_result.found,
            "trimmed": False,
            "reason": None,
        }

        # 合并 ACNR resolve 结果
        if resolve_result.found:
            response["addr_id"] = resolve_result.addr_id
            response["entry_type"] = resolve_result.entry_type
            if resolve_result.jump_route:
                response["jump_route"] = resolve_result.jump_route

        # 合并 render_registry 原有字段
        if entry is not None:
            response.update(entry)

        return response

    except Exception as e:
        # R13.5: 转发失败返回错误，**不回退旧逻辑**
        logger.error("ACNR 转发失败 render-registry/%s: %s", wp_code, e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"ACNR 解析服务转发失败: {e!s}",
        ) from e


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
