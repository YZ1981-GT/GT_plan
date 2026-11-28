"""账号角色绑定 API（dept-role-data-permission Task 9.2）

prefix=/api/system/user-roles，全部端点要求 `require_role(["admin"])`。

Validates: Requirements 4.1, 4.2, 4.3, 5.4
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import require_role
from app.models.core import User
from app.services import user_role_service
from app.services.login_user_service import invalidate_login_user_by_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/user-roles", tags=["系统管理-账号角色"])


class AssignRolesRequest(BaseModel):
    """绑定角色请求（覆盖写）。

    ⚠️ `role_ids` 为 `[]` 是**合法**的，表示清空该账号的全部角色绑定。
       此后该账号的 effective_data_scope 由 `users.role` 枚举对应的
       seed 角色决定（Req 10.5），**不是**"没有任何权限"。
    """

    role_ids: list[int] = Field(
        default_factory=list, description="角色 id 列表（覆盖写，空列表=清空绑定）"
    )


class BoundRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role_key: str
    data_scope: int


@router.get("/{user_id}", response_model=list[BoundRoleResponse])
async def get_user_roles(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> list[BoundRoleResponse]:
    """查该账号绑定的全部未删除角色（Req 4.2）。"""
    roles = await user_role_service.get_user_roles(db, user_id)
    return [BoundRoleResponse.model_validate(r) for r in roles]


@router.put("/{user_id}/roles", response_model=list[int])
async def assign_user_roles(
    user_id: UUID,
    body: AssignRolesRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> list[int]:
    """覆盖写该账号的角色绑定（Req 4.1/4.3）+ 失效其缓存（Req 5.4）。

    Returns:
        实际生效的角色 id 列表（= 入参去重后，已排序）

    🔴 **失效必须在 commit 之后**：若在 commit 前失效，另一个并发请求可能在
       "缓存已清、数据未提交"的窗口里重组出**旧**权限并写回缓存 ⇒ 白失效一次，
       该账号会继续用旧权限直到 TTL 到期。

    ⚠️ 服务层会在校验失败时抛 400/404（整批拒绝），此时**不会**执行到
       commit 与失效 —— 数据与缓存都保持原样，这是正确的。
    """
    applied = await user_role_service.assign_roles(db, user_id, body.role_ids)
    await db.commit()

    redis = await get_redis()
    n = await invalidate_login_user_by_user(user_id, redis)
    logger.info(
        "[user_role] 账号 %s 角色已更新为 %s，失效 %d 个缓存会话",
        user_id, sorted(applied), n,
    )
    return sorted(applied)
