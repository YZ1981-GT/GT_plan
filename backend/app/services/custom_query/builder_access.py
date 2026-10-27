"""高级构建器准入判定（advanced-query-linkage-closure 任务 12；ADR-AQL-08，design §3.4；R3.6、R11.3）。

准入的唯一实现：路由门禁 ``routers/query_builder.require_query_builder_access`` 与 ``GET /api/query/access`` 都调本模块，
前端入口按 access 接口的结论置灰并显示同一条原因（R3.6：前后端同源）。

- 准入：系统角色 ∈ {admin, partner, manager}（``basis = "system_role"``），或在至少一个未删除项目里有一条未删除成员行、
  项目角色 ∈ {manager, partner} 且权限级别 edit（``basis = "project_manager"``）。改造前只认系统角色，系统角色为
  auditor 的现场项目经理被挡在外面（AQ-21），403 文案还漏了合伙人（AQ-29）。
- 作用域与准入分开：准入通过只说明能用构建器，能查哪些项目由 ``builder_scope.resolve_builder_scope`` 决定（与执行时
  同一函数）。access 接口的 ``accessible_project_count`` 就取它的结果，不另数；admin / partner 不限项目，计数为 ``None``。
- 准入通过而作用域为空时 ``allowed`` 仍为真、计数为 0，``reason`` 写明原因（前端置灰显示）；后端执行时照常得 0 行，
  不另设第二套准入口径。
- PII 列仍按系统角色判定（``table_whitelist.PII_ALLOWED_ROLES``），项目经理看不到人员表的电话、邮箱。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import PermissionLevel, Project, ProjectUser, ProjectUserRole

#: 凭系统角色即可使用构建器（partner 为 manager 的权限超集，平台既有约定）
SYSTEM_BUILDER_ROLES: tuple[str, ...] = ("admin", "manager", "partner")
#: 凭项目成员行使用构建器：项目角色 ∈ 此集合且权限级别为 edit
PROJECT_BUILDER_ROLES: tuple[ProjectUserRole, ...] = (ProjectUserRole.manager, ProjectUserRole.partner)
#: 不限项目的系统角色（与 ``ownership_guard`` 的「可访问全部项目」同口径）
ALL_PROJECT_ROLES: tuple[str, ...] = ("admin", "partner")

#: 没有构建器准入时的原因（403 ``ROLE_FORBIDDEN`` 与 access 接口共用）
FORBIDDEN_REASON = "高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用"
#: 准入通过但没有任何可访问的未删除项目
NO_PROJECT_REASON = "您当前没有可访问的项目"

Basis = Literal["system_role", "project_manager"]


@dataclass(frozen=True)
class BuilderAdmission:
    """准入结论：``basis`` 为准入依据（不准入时为 ``None``）。"""

    allowed: bool
    basis: Basis | None


@dataclass(frozen=True)
class BuilderAccess:
    """``GET /api/query/access`` 的响应：准入结论 + 作用域规模 + 置灰原因。"""

    allowed: bool
    basis: Basis | None
    reason: str | None
    all_projects: bool
    accessible_project_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def role_value(user: Any) -> str:
    """系统角色的字符串值（枚举取 ``.value``，与 ``routers/query_builder._get_role_value`` 同口径）。"""
    role = getattr(user, "role", "")
    return str(role.value if hasattr(role, "value") else role or "")


async def _is_project_builder(user: Any, db: AsyncSession) -> bool:
    """在未删除项目里有一条未删除成员行：项目角色 ∈ {manager, partner} 且权限级别 edit。"""
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    stmt = (
        select(ProjectUser.id)
        .join(Project, Project.id == ProjectUser.project_id)
        .where(
            ProjectUser.user_id == user_id,
            ProjectUser.is_deleted == false(),
            Project.is_deleted == false(),
            ProjectUser.role.in_(PROJECT_BUILDER_ROLES),
            ProjectUser.permission_level == PermissionLevel.edit,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).first() is not None


async def builder_admission(user: Any, db: AsyncSession) -> BuilderAdmission:
    """构建器准入判定（路由门禁与 access 接口共用的唯一实现）。系统角色命中时不查库。"""
    if role_value(user) in SYSTEM_BUILDER_ROLES:
        return BuilderAdmission(True, "system_role")
    if await _is_project_builder(user, db):
        return BuilderAdmission(True, "project_manager")
    return BuilderAdmission(False, None)


async def resolve_builder_access(user: Any, db: AsyncSession) -> BuilderAccess:
    """准入结论 + 构建器作用域内的项目数（与执行时同一函数 ``resolve_builder_scope``）。"""
    from app.services.custom_query.builder_scope import resolve_builder_scope

    admission = await builder_admission(user, db)
    if not admission.allowed:
        return BuilderAccess(False, None, FORBIDDEN_REASON, False, 0)
    if role_value(user) in ALL_PROJECT_ROLES:
        return BuilderAccess(True, admission.basis, None, True, None)
    scope = await resolve_builder_scope(user=user, dsl_tables=(), db=db)
    count = len(scope.project_ids or ())
    return BuilderAccess(True, admission.basis, None if count else NO_PROJECT_REASON, False, count)
