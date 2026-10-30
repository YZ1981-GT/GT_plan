"""User_Role_Service —— 账号多角色绑定（dept-role-data-permission Task 5）

职责：`sys_user_role` 的覆盖写与查询。账号的数据权限由其**全部**角色共同决定
（多角色取最大权限，见 `data_scope_service.compute_effective_data_scope`）。

服务层只 `flush` 不 `commit`，由路由层统一 `commit`（项目铁律）。

Validates: Requirements 4.1, 4.2, 4.3
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.sys_permission import SysRole, SysUserRole
from app.services.role_service import ERR_ROLE_NOT_FOUND

logger = logging.getLogger(__name__)

__all__ = [
    "ERR_ROLE_NOT_FOUND",
    "ERR_USER_NOT_FOUND",
    "assign_roles",
    "get_user_role_ids",
    "get_user_role_scopes",
    "get_user_roles",
]

ERR_USER_NOT_FOUND = "账号不存在"


async def _assert_user_exists(db: AsyncSession, user_id: UUID) -> None:
    """账号必须存在且未软删。

    需求未明写，但必须校验：`fk_sys_user_role_user` 外键存在，
    传幽灵 user_id 会 IntegrityError → 未捕获的 500。
    """
    exists = (
        await db.execute(
            select(User.id).where(
                User.id == user_id,
                User.is_deleted == False,  # noqa: E712
            )
        )
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)


async def _assert_all_roles_exist(db: AsyncSession, role_ids: Iterable[int]) -> set[int]:
    """所有 role_id 必须存在且未删除，否则**整批拒绝**（Req 4.3）。

    🔴 「整批拒绝」而非「跳过非法项」是需求明确要求的，也是唯一安全的语义：
       若静默跳过，管理员提交 [1, 999] 会得到"绑定成功"却只生效了角色 1，
       而界面显示两个都绑上了 —— 权限配置与实际不符，且无任何报错线索。
    """
    unique = {int(r) for r in role_ids}
    if not unique:
        return set()

    rows = await db.execute(
        select(SysRole.id).where(
            SysRole.id.in_(unique),
            SysRole.is_deleted == False,  # noqa: E712
        )
    )
    existing = {r[0] for r in rows.all()}
    missing = unique - existing
    if missing:
        # 文案按 Req 4.3 逐字为"角色不存在"；附上具体 id 便于排查，
        # 但保证 detail 以该文案开头，前端可直接前缀匹配。
        raise HTTPException(
            status_code=400,
            detail=f"{ERR_ROLE_NOT_FOUND}: {', '.join(str(i) for i in sorted(missing))}",
        )
    return unique


async def assign_roles(
    db: AsyncSession, user_id: UUID, role_ids: Sequence[int]
) -> set[int]:
    """覆盖写账号的角色绑定：**先全删、再按新集合插入**（Req 4.1）。

    Args:
        user_id: 账号 id
        role_ids: 新的角色 id 列表（允许重复、允许空列表）

    Returns:
        实际生效的角色 id 集合（= 入参去重后）

    幂等（Property 4 的 sys_user_role 子场景）：结果只取决于 `role_ids` 去重后的集合，
    与调用次数、原有绑定、传入顺序均无关。

    空列表语义：**清空该账号的全部角色绑定**（合法操作）。此后该账号的
    effective_data_scope 由 `users.role` 枚举对应的 seed 角色决定（Req 10.5）。

    ⚠️ 校验必须**先于**任何删除操作：否则「角色不存在」的请求会先把旧绑定删掉、
       再抛异常。虽然路由层未 commit 时会回滚，但同一 session 内的后续查询
       会看到已被删空的中间状态。

    ⚠️ 调用方必须随后调 `invalidate_login_user_by_user(user_id)` 失效该账号的
       LoginUser 缓存（Req 5.4），否则已登录会话仍用旧权限直到 TTL 到期。

    Raises:
        HTTPException 404: 账号不存在
        HTTPException 400: 角色 id 列表中有不存在或已删除的角色（整批拒绝）
    """
    await _assert_user_exists(db, user_id)
    wanted = await _assert_all_roles_exist(db, role_ids)

    # 校验都过了才开始改数据
    await db.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
    for rid in wanted:
        db.add(SysUserRole(user_id=user_id, role_id=rid))
    await db.flush()

    logger.info(
        "[user_role] 账号 %s 的角色绑定已覆盖写为 %s（共 %d 个）",
        user_id, sorted(wanted), len(wanted),
    )
    return wanted


async def get_user_role_ids(db: AsyncSession, user_id: UUID) -> list[int]:
    """取账号绑定的全部**未删除**角色 id（Req 4.2）。

    JOIN `sys_role` 过滤软删角色：`delete_role` 虽会清理 `sys_user_role`，
    但若有人直接在库里软删角色（或历史脏数据），绑定行会残留 ⇒
    不过滤会让已删角色继续参与 data_scope 计算。
    """
    rows = await db.execute(
        select(SysUserRole.role_id)
        .join(SysRole, SysRole.id == SysUserRole.role_id)
        .where(
            SysUserRole.user_id == user_id,
            SysRole.is_deleted == False,  # noqa: E712
        )
        .order_by(SysUserRole.role_id)
    )
    return [r[0] for r in rows.all()]


async def get_user_roles(db: AsyncSession, user_id: UUID) -> list[SysRole]:
    """取账号绑定的全部未删除角色对象（供 API 返回角色名等信息）。"""
    rows = await db.execute(
        select(SysRole)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(
            SysUserRole.user_id == user_id,
            SysRole.is_deleted == False,  # noqa: E712
        )
        .order_by(SysRole.id)
    )
    return list(rows.scalars().all())


async def get_user_role_scopes(db: AsyncSession, user_id: UUID) -> list[int]:
    """取账号全部未删除角色的 data_scope 列表。

    这是喂给 `compute_effective_data_scope` 的直接输入（Task 7.2 会用）。
    只启用状态的角色参与？—— **不**：需求未要求按 status 过滤，
    且 status 是"停用"而非"删除"语义。若日后要按 status 过滤，
    必须同时改 Req 4.2 与 Property 6 的表述，不能只改这里。
    """
    rows = await db.execute(
        select(SysRole.data_scope)
        .join(SysUserRole, SysUserRole.role_id == SysRole.id)
        .where(
            SysUserRole.user_id == user_id,
            SysRole.is_deleted == False,  # noqa: E712
        )
    )
    return [r[0] for r in rows.all()]
