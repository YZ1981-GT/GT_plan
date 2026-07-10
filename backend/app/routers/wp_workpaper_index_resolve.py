"""底稿实例解析端点（Legacy 转发）

GET /api/workpapers/index-resolve/{wpCode}

M1: 转发至 ACNR resolve_instance 统一出口（R13.1, R13.2, R13.4, R13.5）。
- 唯一 wp_id 解析出口
- 一次查询返回 exists / trimmed / reason
- 转发失败返回错误，不回退旧逻辑

Requirements: 13.1, 13.2, 13.4, 13.5
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.acnr.grammar import STANDARD_WP_CODE_RE
from app.services.acnr.resolver import resolve_instance

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/index-resolve",
    tags=["wp-index-resolve-legacy"],
)


@router.get("/{wp_code}")
async def resolve_workpaper_index(
    wp_code: str,
    project_id: UUID = Query(..., description="项目 UUID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """解析底稿实例 — 转发至 ACNR resolve_instance（唯一 wp_id 出口）。

    M1 转发逻辑（R13.1, R13.2, R13.4, R13.5）：
    - 从 wp_code 提取 parent_wp_code 和 sheet_code
    - 调用 ACNR resolve_instance 获取 wp_id + jump_route
    - 一次查询返回 exists / trimmed / reason（R13.4）
    - 转发失败返回错误，不回退旧逻辑（R13.5）

    Args:
        wp_code: 底稿编码（如 D2-2、D2）
        project_id: 项目 UUID

    Returns:
        {exists: bool, wp_id?: str, jump_route?: str, trimmed: bool, reason?: str}
    """
    try:
        # 从 wp_code 提取 parent_wp_code（R8.6: WP 第一参）
        # D2-2 → parent=D2, sheet=D2-2
        # D2 → parent=D2, sheet=D2
        parent_wp_code = _extract_parent(wp_code)
        sheet_code = wp_code.upper()

        # 转发至 ACNR resolve_instance（R13.1: 唯一 wp_id 出口）
        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code=parent_wp_code,
            sheet_code=sheet_code,
        )

        # 构建响应（R13.4: 一次查询返回 exists/trimmed/reason）
        response: dict = {
            "exists": result.found,
            "trimmed": False,
            "reason": None,
        }

        if result.found:
            response["wp_id"] = str(result.wp_id) if result.wp_id else None
            response["jump_route"] = result.jump_route
            response["wp_index_id"] = str(result.wp_index_id) if result.wp_index_id else None
        else:
            response["error"] = result.error
            if result.candidates:
                response["candidates"] = result.candidates

        # 检查裁剪状态
        trimmed, reason = await _check_trimmed_status(db, project_id, sheet_code)
        response["trimmed"] = trimmed
        response["reason"] = reason

        return response

    except Exception as e:
        # R13.5: 转发失败返回错误，**不回退旧逻辑**
        logger.error(
            "ACNR 转发失败 index-resolve/%s: %s", wp_code, e, exc_info=True
        )
        raise HTTPException(
            status_code=502,
            detail=f"ACNR 解析服务转发失败: {e!s}",
        ) from e


# ─── Helpers ─────────────────────────────────────────────────────────────────


import re

# 从 grammar_v1 导入的标准底稿码正则
_PARENT_RE = re.compile(r"^([A-S]\d+)", re.IGNORECASE)


def _extract_parent(wp_code: str) -> str:
    """从 wp_code 提取 parent_wp_code。

    D2-2 → D2
    D2 → D2
    A1-17 → A1
    """
    upper = wp_code.upper()
    match = _PARENT_RE.match(upper)
    if match:
        return match.group(1)
    return upper


async def _check_trimmed_status(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
) -> tuple[bool, str | None]:
    """检查底稿裁剪状态。"""
    from sqlalchemy import select
    from app.models.procedure_models import ProcedureInstance

    try:
        stmt = select(ProcedureInstance).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.wp_code == wp_code,
            ProcedureInstance.status == "not_applicable",
            ProcedureInstance.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        trim_instance = result.scalar_one_or_none()

        if trim_instance:
            return (True, trim_instance.skip_reason)
    except Exception as e:
        logger.warning("检查裁剪状态失败 wp_code=%s: %s", wp_code, e)

    return (False, None)
