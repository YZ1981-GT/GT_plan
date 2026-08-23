"""白名单构建器的项目作用域注入（R2）。

设计对应 `.kiro/specs/advanced-query-hardening-wiring-closure/design.md` §Components 2。

**存在理由（浏览器 + 认证 token 双实测）**：改造前 ``routers/query_builder.py``
全链路零 ``project_id`` 注入 —— ``_build_select`` 只做表 / 列 / 算子白名单，
``current_user`` 仅用于缓存键。实测以合法 token 请求
``POST /api/query/execute {"table": "trial_balance", "fields": ["project_id"],
"limit": 1000}``，返回的 1000 行**覆盖 9 个不同项目**；而 ``projects`` 表在白名单内，
一次查询即可跨全部客户。缓存键更写死 ``project_id="__query_builder__"``，
不同可访问范围的用户共用同一命名空间。

作用域来源复用 ``OwnershipGuard.get_accessible_project_ids``（已存在的公开出口），
不新写第二套项目可见性判定。

_Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_query.ownership_guard import ownership_guard
from app.services.custom_query.table_whitelist import TABLE_WHITELIST

logger = logging.getLogger(__name__)

#: 不含 ``project_id`` 列的全局配置表 —— 跳过项目过滤并在 warnings 明示（R2.3）。
#: 这类表是平台级模板/配置（对所有项目相同），不加过滤不构成越权。
GLOBAL_CONFIG_TABLES: frozenset[str] = frozenset({"report_config"})

#: 作用域过滤所用的列名
SCOPE_COLUMN = "project_id"


@dataclass(frozen=True)
class BuilderScope:
    """一次构建器查询的生效作用域。

    ``project_ids is None`` 表示「全项目可访问」（admin / partner），此时不加过滤
    但仍要在响应中标注实际作用域，避免「看到了全平台数据却不知道」（R2.2）。
    """

    project_ids: frozenset[UUID] | None
    unscoped_tables: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_all_projects(self) -> bool:
        return self.project_ids is None

    def describe(self) -> dict[str, Any]:
        """响应用的作用域说明（前端可展示「本次查询范围」）。"""
        return {
            "all_projects": self.is_all_projects,
            "project_count": None if self.is_all_projects else len(self.project_ids or ()),
            "unscoped_tables": list(self.unscoped_tables),
        }


def _scope_column(table_name: str) -> Any | None:
    """取该表的 project_id 列；表无此列返回 None。"""
    meta = TABLE_WHITELIST.get(table_name)
    if not meta:
        return None
    if SCOPE_COLUMN not in (meta.get("fields") or ()):
        return None
    return getattr(meta["model"], SCOPE_COLUMN, None)


def table_is_scopable(table_name: str) -> bool:
    """该表是否可施加项目作用域过滤。"""
    return _scope_column(table_name) is not None


async def resolve_builder_scope(
    *,
    user: Any,
    dsl_tables: Iterable[str],
    requested_project_id: Any = None,
    db: AsyncSession,
) -> BuilderScope:
    """解析本次查询的生效作用域（R2.1 / R2.2 / R2.3 / R2.5）。

    - admin / partner → ``project_ids=None``（全项目），仍标注作用域；
    - 其余角色 → 可访问项目集合；集合为空时 fail-closed 403（无可查项目时返回空
      结果会被误读为「这些表没数据」）；
    - 显式指定 ``requested_project_id`` 且不可访问 → 403，且不执行查询（R2.5）；
    - 命中全局配置表 → 记入 ``unscoped_tables`` 并产出 warning（R2.3）。
    """
    tables = [str(t) for t in dsl_tables if t]
    unscoped = tuple(
        t for t in tables if t in GLOBAL_CONFIG_TABLES or not table_is_scopable(t)
    )
    warnings: list[str] = []
    for table_name in unscoped:
        warnings.append(
            f"表 '{table_name}' 无项目维度（平台级配置），本次查询未按项目过滤"
        )

    accessible = await ownership_guard.get_accessible_project_ids(user, db)

    if requested_project_id:
        # 显式指定项目：走既有守卫（含 RLS context 设置与越权审计）
        await ownership_guard.assert_target_accessible(
            user=user, project_id=requested_project_id, db=db
        )
        pid = _to_uuid(requested_project_id)
        if pid is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FORBIDDEN_PROJECT",
                    "message": "目标项目标识无效，拒绝访问",
                },
            )
        return BuilderScope(
            project_ids=frozenset({pid}),
            unscoped_tables=unscoped,
            warnings=tuple(warnings),
        )

    if accessible is None:
        warnings.append("当前角色可访问全部项目，本次查询未限定项目范围")
        return BuilderScope(
            project_ids=None, unscoped_tables=unscoped, warnings=tuple(warnings)
        )

    if not accessible:
        # 空集合：注入永假过滤（`project_id IN ()`）而非 403。
        # 选空结果而非拒绝，是因为 403 会把「你没有项目」与「你没权限用构建器」
        # 混成同一个提示；而空结果 + 明确 warning 能让用户知道该去要项目分派。
        # 安全性等价 —— 永假条件不会返回任何行。
        warnings.append(
            "当前账号未被分派任何项目，查询范围为空；请联系项目经理分派后重试"
        )

    return BuilderScope(
        project_ids=frozenset(accessible),
        unscoped_tables=unscoped,
        warnings=tuple(warnings),
    )


def _to_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def apply_scope_to_select(
    stmt: Select, *, scope: BuilderScope, table_name: str
) -> Select:
    """把作用域约束追加到 ``SELECT``（R2.1）。

    调用点必须是 WHERE 组装的**最后一步**：追加而非合并，用户 DSL 里即便自己写了
    ``project_id`` 过滤也只会与本约束取交集，无法放宽（AND 语义）。
    """
    if scope.is_all_projects:
        return stmt
    column = _scope_column(table_name)
    if column is None:
        return stmt  # 全局配置表：无 project_id 列，跳过（已在 warnings 标注）
    return stmt.where(column.in_(list(scope.project_ids or ())))


def scope_signature(scope: BuilderScope) -> str:
    """作用域的稳定签名，纳入缓存键（R2.4）。

    改造前缓存键写死 ``project_id="__query_builder__"`` —— 两个可访问项目集合不同
    的用户对同一 DSL 会命中同一条缓存，等于跨作用域泄漏。
    """
    if scope.is_all_projects:
        return "all"
    joined = ",".join(sorted(str(pid) for pid in (scope.project_ids or ())))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]
