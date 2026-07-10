"""ACNR Resolver — resolve_instance + ProjectBinding

resolve_instance(project_id, parent_wp_code, sheet_code) 是平台唯一的 wp_id
解析出口 (R13.1)。通过运行时查询 WpIndex → WorkingPaper 链实现 ProjectBinding。

M1 阶段 ProjectBinding 为运行时查询（非物化缓存），M2+ 可选 DB 物化。

Requirements: 6.1, 6.2, 6.3, 6.4, 13.1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpIndex, WorkingPaper
from app.services.acnr.catalog import get_catalog

logger = logging.getLogger(__name__)


# ─── Result Types ─────────────────────────────────────────────────────────────


@dataclass
class ProjectBinding:
    """L2 ProjectBinding — 运行时解析结果。

    Fields per design.md §ProjectBinding:
    - project_id: 项目 UUID
    - parent_wp_code: 父底稿码（WP() 第一参）
    - sheet_code: Tab 编码
    - wp_id: 解析到的 WorkingPaper 实例 UUID
    - wp_index_id: WpIndex 条目 UUID
    - resolved_at: 解析时刻
    """

    project_id: UUID
    parent_wp_code: str
    sheet_code: str
    wp_id: UUID
    wp_index_id: UUID
    resolved_at: datetime


@dataclass
class ResolveInstanceResult:
    """resolve_instance 返回值。"""

    found: bool
    wp_id: Optional[UUID] = None
    wp_index_id: Optional[UUID] = None
    jump_route: Optional[str] = None
    binding: Optional[ProjectBinding] = None
    error: Optional[str] = None
    candidates: Optional[list[dict]] = None


# ─── Core resolver function ───────────────────────────────────────────────────


async def resolve_instance(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    *,
    explicit_wp_id: Optional[UUID] = None,
) -> ResolveInstanceResult:
    """解析项目内 wp_id — 唯一 wp_id 出口 (R13.1)。

    逻辑：
    1. 查 WpIndex 表：project_id 匹配 AND wp_code 匹配 sheet_code
       (因为 WpIndex.wp_code 对应 sheet 级编码如 "D2-2")
    2. 恰好 1 条 → 查 WorkingPaper 获取 wp_id → 返回 jump_route + wp_id
    3. 多条 → disambiguation error (R6.3)，除非 explicit_wp_id
    4. 0 条 → not found

    Args:
        db: 异步数据库会话
        project_id: 项目 UUID
        parent_wp_code: 父底稿码（如 D2），用于 jump_route 与 catalog 查找
        sheet_code: Tab 编码（如 D2-2），用于 WpIndex 查询
        explicit_wp_id: 调用方显式传入的 wp_id，多实例时跳过消歧

    Returns:
        ResolveInstanceResult
    """
    # ─── R6.3: 显式传入 wp_id 时直接验证并返回 ───────────────────────────
    if explicit_wp_id is not None:
        return await _resolve_with_explicit_wp_id(
            db, project_id, parent_wp_code, sheet_code, explicit_wp_id
        )

    # ─── Step 1: 查 WpIndex ──────────────────────────────────────────────
    stmt = (
        sa.select(WpIndex)
        .where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == sheet_code,
            WpIndex.is_deleted == sa.false(),
        )
    )
    result = await db.execute(stmt)
    indices = result.scalars().all()

    # ─── Step 4: 0 条 → not found ────────────────────────────────────────
    if not indices:
        logger.debug(
            "resolve_instance miss: project=%s parent=%s sheet=%s",
            project_id, parent_wp_code, sheet_code,
        )
        return ResolveInstanceResult(found=False, error="not_found")

    # ─── Step 3: 多条 → disambiguation error (R6.3) ──────────────────────
    if len(indices) > 1:
        candidates = [
            {
                "wp_index_id": str(idx.id),
                "wp_code": idx.wp_code,
                "wp_name": idx.wp_name,
            }
            for idx in indices
        ]
        return ResolveInstanceResult(
            found=False,
            error="disambiguation",
            candidates=candidates,
        )

    # ─── Step 2: 恰好 1 条 → 获取 wp_id ─────────────────────────────────
    wp_index_entry = indices[0]
    return await _resolve_single_index(
        db, project_id, parent_wp_code, sheet_code, wp_index_entry
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


async def _resolve_single_index(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    wp_index_entry: WpIndex,
) -> ResolveInstanceResult:
    """从单个 WpIndex 条目解析到 wp_id + jump_route。"""
    # 查 WorkingPaper：通过 wp_index_id 定位底稿实例
    wp_stmt = (
        sa.select(WorkingPaper.id)
        .where(
            WorkingPaper.wp_index_id == wp_index_entry.id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        .limit(1)
    )
    wp_result = await db.execute(wp_stmt)
    wp_id_row = wp_result.scalar_one_or_none()

    if wp_id_row is None:
        # WpIndex 存在但 WorkingPaper 未创建（底稿未生成）
        return ResolveInstanceResult(
            found=False,
            wp_index_id=wp_index_entry.id,
            error="working_paper_not_created",
        )

    wp_id = wp_id_row

    # 构建 jump_route (R6.2)
    jump_route = _build_jump_route(project_id, wp_id, parent_wp_code, sheet_code)

    # 构建 ProjectBinding
    binding = ProjectBinding(
        project_id=project_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        wp_id=wp_id,
        wp_index_id=wp_index_entry.id,
        resolved_at=datetime.now(timezone.utc),
    )

    return ResolveInstanceResult(
        found=True,
        wp_id=wp_id,
        wp_index_id=wp_index_entry.id,
        jump_route=jump_route,
        binding=binding,
    )


async def _resolve_with_explicit_wp_id(
    db: AsyncSession,
    project_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
    explicit_wp_id: UUID,
) -> ResolveInstanceResult:
    """R6.3: 显式传入 wp_id 时直接验证并返回。

    验证 wp_id 确实属于该项目且未删除。
    """
    wp_stmt = (
        sa.select(WorkingPaper)
        .where(
            WorkingPaper.id == explicit_wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        )
    )
    wp_result = await db.execute(wp_stmt)
    wp = wp_result.scalar_one_or_none()

    if wp is None:
        return ResolveInstanceResult(
            found=False,
            error="explicit_wp_id_not_found",
        )

    # 构建 jump_route
    jump_route = _build_jump_route(project_id, explicit_wp_id, parent_wp_code, sheet_code)

    binding = ProjectBinding(
        project_id=project_id,
        parent_wp_code=parent_wp_code,
        sheet_code=sheet_code,
        wp_id=explicit_wp_id,
        wp_index_id=wp.wp_index_id,
        resolved_at=datetime.now(timezone.utc),
    )

    return ResolveInstanceResult(
        found=True,
        wp_id=explicit_wp_id,
        wp_index_id=wp.wp_index_id,
        jump_route=jump_route,
        binding=binding,
    )


def _build_jump_route(
    project_id: UUID,
    wp_id: UUID,
    parent_wp_code: str,
    sheet_code: str,
) -> str:
    """构建跳转路由（R6.2）。

    使用 catalog 的 jump_route_template（如有），否则构建默认路由。
    模板格式: /workpapers/{wp_id}?sheet={sheet_code}
    """
    # 尝试从 catalog 获取 jump_route_template
    cat = get_catalog()
    sheet_addr_id = f"{parent_wp_code}/{sheet_code}"
    sheet_entry = cat.sheets_by_addr_id.get(sheet_addr_id)

    if sheet_entry:
        template = sheet_entry.get("jump_route_template", "")
        if template:
            # 替换模板中的 {wp_id} 占位符
            return template.replace("{wp_id}", str(wp_id))

    # 默认路由模板
    return f"/workpapers/{wp_id}?sheet={sheet_code}"
