"""角色与数据权限管理 API（dept-role-data-permission Task 9.1）

prefix=/api/system/roles，全部端点要求 `require_role(["admin"])`。

🔴 **本模块承担两件服务层做不到的事**：
  1. **commit**：服务层只 `flush`（项目铁律），事务边界归路由层
  2. **缓存失效**：改了角色的 data_scope 或项目关联后，必须失效**所有绑定该角色
     的账号**的 LoginUser 缓存（Req 5.4），否则已登录会话会继续用旧权限直到
     TTL 到期（30 分钟）—— 一个"改了权限但不生效"的故障。

⚠️ **失效必须在 commit 之后**：若在 commit 前失效，另一个并发请求可能在
   "缓存已清、数据未提交"的窗口里重组出**旧**权限并写回缓存 ⇒ 白失效一次。

⚠️ **`delete_role` 的账号列表必须在删除前反查**：`delete_role` 会清掉
   `sys_user_role`，删完就查不到谁绑过它了。

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import require_role
from app.models.core import User
from app.models.sys_permission import ROLE_STATUS_ENABLED
from app.services import role_service
from app.services.login_user_service import invalidate_login_user_by_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/roles", tags=["系统管理-角色"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RoleCreateRequest(BaseModel):
    """创建角色请求。

    🔴 **`data_scope` 刻意不加 `ge/le` 约束**（项目铁律）：
       Pydantic 的范围校验返回 **422** 且文案由框架生成，而 Req 3.2 明确要求
       **400 + "数据权限范围取值非法"**。校验的唯一入口在
       `role_service.validate_data_scope`。
    """

    name: str = Field(..., description="角色名称")
    role_key: str = Field(..., description="角色标识（未删除范围内唯一）")
    data_scope: int = Field(..., description="数据权限范围，仅接受 1/2/5")
    status: str = Field(default=ROLE_STATUS_ENABLED, description="0=启用 1=停用")
    project_ids: list[UUID] | None = Field(
        default=None, description="data_scope=2 时的自定义项目 id 列表"
    )


class RoleUpdateRequest(BaseModel):
    """修改角色请求。

    🔴 **全部字段可选，`None` = "本次不改该字段"**。
       `project_ids` 的 `None` 与 `[]` **语义不同**：前者保持原关联，
       后者清空。若把 None 也当清空，"只改角色名"的请求会把项目配置全抹掉。
    """

    name: str | None = None
    role_key: str | None = None
    data_scope: int | None = None
    status: str | None = None
    project_ids: list[UUID] | None = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role_key: str
    data_scope: int
    status: str


# ---------------------------------------------------------------------------
# 缓存失效
# ---------------------------------------------------------------------------


async def _invalidate_bound_accounts(user_ids: list[UUID]) -> int:
    """失效这批账号的 LoginUser 缓存（Req 5.4）。

    ⚠️ Redis 不可用时 `invalidate_login_user_by_user` 返回 0 且不抛错 ——
       此时压根没有缓存需要失效（`get_login_user` 每次现算），语义上等价于
       "已全部失效"。故本函数也不因此报错。
    """
    if not user_ids:
        return 0
    redis = await get_redis()
    total = 0
    for uid in user_ids:
        total += await invalidate_login_user_by_user(uid, redis)
    if total:
        logger.info("[sys_role] 已失效 %d 个账号的 %d 个缓存会话", len(user_ids), total)
    return total


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> list[RoleResponse]:
    """角色列表（仅未删除），含 data_scope（Req 3.6）。"""
    roles = await role_service.list_roles(db)
    return [RoleResponse.model_validate(r) for r in roles]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> RoleResponse:
    """创建角色（Req 3.1/3.2/3.3/3.4）。

    新建角色尚无账号绑定 ⇒ **无需失效任何缓存**。
    """
    role = await role_service.create_role(
        db,
        name=body.name,
        role_key=body.role_key,
        data_scope=body.data_scope,
        status=body.status,
        project_ids=body.project_ids,
    )
    await db.commit()
    await db.refresh(role)
    return RoleResponse.model_validate(role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    body: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> RoleResponse:
    """修改角色（Req 3.2~3.5）+ 失效受影响账号的缓存（Req 5.4）。

    ⚠️ 账号列表**在修改前**反查即可（修改不会动 `sys_user_role`），
       但**失效动作必须在 commit 之后**，见模块头说明。
    """
    affected = await role_service.get_user_ids_by_role(db, role_id)

    role = await role_service.update_role(
        db,
        role_id,
        name=body.name,
        role_key=body.role_key,
        data_scope=body.data_scope,
        status=body.status,
        project_ids=body.project_ids,
    )
    await db.commit()
    await db.refresh(role)

    await _invalidate_bound_accounts(affected)
    return RoleResponse.model_validate(role)


@router.get("/{role_id}/projects", response_model=list[UUID])
async def get_role_projects(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> list[UUID]:
    """取角色的自定义项目 id 列表（已过滤软删项目）。"""
    return await role_service.get_role_project_ids(db, role_id)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # 🔴 `response_model=None` 不可省：本模块有 `from __future__ import annotations`，
    #    `-> None` 会被 `get_type_hints` 解析成 **`NoneType` 类**（真值为 True），
    #    FastAPI 便当它是一个 response_model，再撞上 204 不许有响应体的断言
    #    ⇒ `AssertionError: Status code 204 must not have a response body`，
    #    **导入期**就炸，整个应用起不来（不是这一个端点 500）。
    #    不带 future import 的模块里 `-> None` 是 falsy 的 `None`，所以其余
    #    10 个 204 端点无需此参数 —— 别照它们的样子把这行删掉。
    response_model=None,
)
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> None:
    """软删角色 + 清关联 + 失效受影响账号缓存（Req 3.6 / 5.4）。

    🔴 **账号列表必须在 `delete_role` 之前反查**：它会清掉 `sys_user_role`，
       删完就查不到谁绑过这个角色了 ⇒ 那些账号的缓存永远不会被失效，
       会继续按已删角色的 data_scope 放行，直到 TTL 到期。
    """
    affected = await role_service.get_user_ids_by_role(db, role_id)

    await role_service.delete_role(db, role_id)
    await db.commit()

    await _invalidate_bound_accounts(affected)
