"""ACNR Auth — 项目授权与 Binding 完整性校验 [Req-3]

check_project_access(user, project_id, session):
    校验当前用户对 project 有访问权（经 project_assignments 或角色）。
    admin / partner 跳过委派检查。

verify_wp_binding(wp_id, project_id, sheet_code, session):
    校验 wp_id 属于 project_id 且 WpIndex.parent_wp_code 与 sheet_code 匹配。

授权失败 → 403（不泄露元数据）。

Requirements: Req-3.1, Req-3.2, Req-3.3
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def check_project_access(user, project_id: str | UUID, session: AsyncSession) -> None:
    """Req-3.1: 校验当前用户对项目有访问权。

    - admin / partner 角色直接放行（可访问全部项目）
    - 其余用户：project_users 或 staff_members→project_assignments 任一命中即可
    - 无权限 → raise HTTPException 403

    与 review_dialog._check_project_access / deps.require_project_access 对齐。
    """
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val in ("admin", "partner"):
        return

    uid = str(user.id)
    pid = str(project_id)

    # 1. 先查 project_users（直接分配）
    pu = (await session.execute(text(
        "SELECT 1 FROM project_users pu "
        "WHERE pu.user_id = :uid AND pu.project_id = :pid "
        "AND pu.is_deleted = false LIMIT 1"
    ), {"uid": uid, "pid": pid})).fetchone()
    if pu is not None:
        return

    # 2. 再查 project_assignments（经 staff_members 关联）
    # 注：project_assignments 的用户列名是 staff_id（不是 user_id）
    pa = (await session.execute(text(
        "SELECT 1 FROM project_assignments pa "
        "JOIN staff_members sm ON sm.id = pa.staff_id "
        "WHERE sm.user_id = :uid AND pa.project_id = :pid "
        "AND pa.is_deleted = false AND sm.is_deleted = false LIMIT 1"
    ), {"uid": uid, "pid": pid})).fetchone()
    if pa is not None:
        return

    # 授权失败 → 403，不泄露元数据 (Req-3.3)
    raise HTTPException(status_code=403, detail="无权访问该项目")


async def verify_wp_binding(
    wp_id: str | UUID,
    project_id: str | UUID,
    sheet_code: str,
    session: AsyncSession,
) -> None:
    """Req-3.2: 校验 wp_id 属于 project_id 且 WpIndex.parent_wp_code 与 sheet_code 匹配。

    三元组校验：
    1. working_paper.id == wp_id AND working_paper.project_id == project_id
    2. working_paper.wp_index_id → wp_index.wp_code 与 sheet_code 匹配
       （wp_index.wp_code 存储 sheet 级编码，如 D2-2）

    不匹配 → raise HTTPException 403，不泄露 wp_id/jump_route 元数据 (Req-3.3)。
    """
    wid = str(wp_id)
    pid = str(project_id)

    # 查 working_paper → wp_index 全链
    row = (await session.execute(text(
        "SELECT wi.wp_code "
        "FROM working_paper wp "
        "JOIN wp_index wi ON wi.id = wp.wp_index_id "
        "WHERE wp.id = :wid AND wp.project_id = :pid "
        "AND wp.is_deleted = false AND wi.is_deleted = false "
        "LIMIT 1"
    ), {"wid": wid, "pid": pid})).fetchone()

    if row is None:
        # wp_id 不属于此 project 或不存在
        raise HTTPException(status_code=403, detail="无权访问该项目")

    # 校验 wp_code (sheet 编码) 匹配
    wp_code_in_db = row[0]
    if wp_code_in_db != sheet_code:
        # binding 三元组不匹配
        raise HTTPException(status_code=403, detail="无权访问该项目")
