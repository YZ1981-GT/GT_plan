"""白名单构建器的项目作用域（advanced-query-hardening-wiring-closure R2；advanced-query-linkage-closure 任务 9，
ADR-AQL-09、design §3.4；R1.2、R3.1~R3.3、R3.5 后端）。

**存在理由（浏览器 + 认证 token 双实测）**：最初 ``routers/query_builder.py`` 全链路零 ``project_id`` 注入，一次查询即可跨
全部客户；hardening 收口后只给**基表**加了 ``project_id IN (可访问集合)``，仍有四处缺口（AQ-02 / AQ-06 / AQ-18）：

- 没有 ``project_id`` 列的表（``projects``、``staff_members``）记入 ``unscoped_tables`` 不过滤 —— 系统经理查 ``projects``
  得到全部项目（含已删）、查 ``staff_members`` 得到全体员工；
- 可访问集合不排除已删项目，JOIN 目标表完全不加作用域、不排除已删行；
- 科目余额表 / 序时账不按生效数据集过滤（同一项目年度的历史数据集一并查出）；
- 请求里指定的项目从未传进来（``QueryDSL`` 没有 ``project_id``），指定了也是查全部可访问项目。

作用域来源仍是 ``OwnershipGuard``（不另写第二套项目可见性判定）；谓词只由 :func:`scope_predicates` 生成：基表的谓词由
:func:`apply_scope_to_select` 在 WHERE 组装的**最后一步**追加（用户 DSL 无法放宽），JOIN 目标表的谓词并入该 JOIN 的 ON
（左连接没有匹配行时目标列为空、基表行保留；放进 WHERE 会把左连接变成内连接）。
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.core import Project
from app.services.custom_query.builder_access import ALL_PROJECT_ROLES, role_value
from app.services.custom_query.cycle_scope import CycleScopeCache
from app.services.custom_query.ownership_guard import ownership_guard
from app.services.custom_query.table_whitelist import (
    DATASET_SCOPED_TABLES,
    ROLE_RESTRICTED_TABLES,
    TABLE_WHITELIST,
)
from app.services.dataset_query import active_rows_predicate

logger = logging.getLogger(__name__)

#: 不含项目维度、但有「项目副本行」的平台级配置表：副本行只对能访问该项目的用户可见
GLOBAL_CONFIG_TABLES: frozenset[str] = frozenset({"report_config"})
#: 报表配置的项目副本行写法（``applicable_standard = 'project:{项目 id}'``）
PROJECT_COPY_PREFIX = "project:"

#: 作用域过滤所用的列名（``projects`` 表本身按 ``id``）
SCOPE_COLUMN = "project_id"

_ROLE_LABELS = {"admin": "管理员", "partner": "合伙人", "manager": "经理"}
EMPTY_SCOPE_WARNING = "当前账号未被分派任何项目，查询范围为空；请联系项目经理分派后重试"
ALL_PROJECTS_WARNING = "当前角色可访问全部项目，本次查询未限定项目范围"
#: 对本人设有审计循环范围的项目不进入构建器作用域（ADR-AQL-19，R3.8）：构建器按表查询、无法按循环过滤
CYCLE_SCOPED_PROJECT = "CYCLE_SCOPED_PROJECT"
CYCLE_SCOPED_PROJECT_MESSAGE = "该项目对您设有审计循环范围，构建器无法按循环过滤，请在业务视图中查询"


def cycle_excluded_warning(count: int) -> str:
    return f"已排除 {count} 个对您设有审计循环范围的项目，请在业务视图中查询"


@dataclass(frozen=True)
class BuilderScope:
    """一次构建器查询的生效作用域。

    ``project_ids is None`` 表示「全部未删除项目」（admin / partner）：仍要排除已删项目，并在响应中标注实际作用域，避免
    「看到了全平台数据却不知道」（R2.2）。``dataset_predicates``：计划中四表（科目余额 / 序时账 / 辅助余额 / 辅助明细）各
    一条生效数据集谓词，由 ``dataset_query.active_rows_predicate`` 预先算好（谓词构造因此保持同步）。
    """

    project_ids: frozenset[UUID] | None
    unscoped_tables: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    requested_project_id: UUID | None = None
    dataset_predicates: Mapping[str, ColumnElement] = field(default_factory=dict)
    #: 本次因循环范围排除的项目数（warning 与 access 接口的 reason 共用）
    excluded_cycle_scoped: int = 0

    @property
    def is_all_projects(self) -> bool:
        return self.project_ids is None

    def describe(self) -> dict[str, Any]:
        """响应用的作用域说明（前端可展示「本次查询范围」）。"""
        return {
            "all_projects": self.is_all_projects,
            "project_count": None if self.is_all_projects else len(self.project_ids or ()),
            "unscoped_tables": list(self.unscoped_tables),
            "requested_project_id": str(self.requested_project_id) if self.requested_project_id else None,
        }


def _table(table_name: str) -> Any | None:
    meta = TABLE_WHITELIST.get(table_name)
    return meta["model"].__table__ if meta else None


def _project_column(table_name: str) -> Any | None:
    """该表的项目列：``projects`` 用 ``id``，其余用 ``project_id``；没有项目维度返回 None。"""
    table = _table(table_name)
    if table is None:
        return None
    if table_name == "projects":
        return table.c.id
    return table.c.get(SCOPE_COLUMN)


def table_is_scopable(table_name: str) -> bool:
    """该表是否可施加项目作用域过滤（``projects`` 按 ``id``）。"""
    return _project_column(table_name) is not None


def _unscoped_warning(table_name: str) -> str:
    if table_name in GLOBAL_CONFIG_TABLES:
        return f"表 '{table_name}' 为平台级配置；项目副本行只含可访问项目"
    return f"表 '{table_name}' 无项目维度（平台级配置），本次查询未按项目过滤"


def _enforce_role_restricted_tables(tables: Iterable[str], user: Any) -> None:
    """人员表等只对限定系统角色开放（基表与 JOIN 目标同样适用，R3.2）。"""
    role = role_value(user)
    for table_name in tables:
        allowed = ROLE_RESTRICTED_TABLES.get(table_name)
        if allowed is None or role in allowed:
            continue
        label = TABLE_WHITELIST[table_name]["label"]
        roles = "、".join(_ROLE_LABELS.get(r, r) for r in sorted(allowed))
        raise HTTPException(
            status_code=403,
            detail={"error_code": "TABLE_ROLE_FORBIDDEN", "message": f"表「{label}」仅对{roles}开放", "table": table_name},
        )


async def _live_project_ids(db: AsyncSession, project_ids: Iterable[Any]) -> frozenset[UUID]:
    """``project_ids`` 中未删除的项目（构建器作用域恒排除已删项目）。"""
    ids = sorted({pid for pid in (_to_uuid(p) for p in project_ids) if pid is not None}, key=str)
    if not ids:
        return frozenset()
    rows = await db.execute(select(Project.id).where(Project.id.in_(ids), Project.is_deleted == false()))
    return frozenset(pid for pid in (_to_uuid(r[0]) for r in rows.all()) if pid is not None)


async def _dataset_predicates(
    db: AsyncSession, tables: Iterable[str], project_ids: frozenset[UUID] | None, year: int | None
) -> dict[str, ColumnElement]:
    """计划中四表各一条生效数据集谓词（查询失败原样上抛，不退化为不按数据集过滤）。"""
    found: dict[str, ColumnElement] = {}
    for table_name in dict.fromkeys(tables):
        table = _table(table_name)
        if table_name in DATASET_SCOPED_TABLES and table is not None:
            found[table_name] = await active_rows_predicate(db, table, project_ids=project_ids, year=year)
    return found


async def _cycle_scoped(user: Any, project_ids: Iterable[UUID], cache: CycleScopeCache) -> frozenset[UUID]:
    """其中对本人设有循环范围的项目（admin / partner 不限，不调用平台入口）。"""
    if role_value(user) in ALL_PROJECT_ROLES:  # 与 CycleScopeCache 的快路径同口径；这里先判，省掉逐项目循环
        return frozenset()
    return frozenset([pid for pid in sorted(project_ids, key=str) if await cache.is_restricted(pid)])


async def resolve_builder_scope(
    *,
    user: Any,
    dsl_tables: Iterable[str],
    requested_project_id: Any = None,
    year: int | None = None,
    db: AsyncSession,
    cycle_cache: CycleScopeCache | None = None,
) -> BuilderScope:
    """解析本次查询的生效作用域（R1.2、R3.1~R3.3、R3.5）。

    - 人员表（基表或 JOIN 目标）对 admin / partner 以外的角色 → 403 ``TABLE_ROLE_FORBIDDEN``，先于一切取数；
    - 显式指定 ``requested_project_id``：经 ``OwnershipGuard`` 校验（含 RLS context 与越权审计），不可访问或已删除 → 403
      ``FORBIDDEN_PROJECT`` 且不执行；作用域只含该项目；
    - 未指定：admin / partner → 全部未删除项目；其余角色 → 可访问集合 − 已删项目；集合为空时作用域为空（永假谓词，
      结果 0 行）并写 warning —— 不报 403，免得把「你没有项目」与「你没权限用构建器」混成同一个提示；
    - 没有项目维度的表记入 ``unscoped_tables`` 并产出 warning（报表配置的项目副本行仍只含可访问项目）。
    """
    tables = [str(t) for t in dsl_tables if t]
    _enforce_role_restricted_tables((t for t in tables if t in TABLE_WHITELIST), user)
    unscoped = tuple(dict.fromkeys(t for t in tables if t in TABLE_WHITELIST and not table_is_scopable(t)))
    warnings = [_unscoped_warning(t) for t in unscoped]
    cache = cycle_cache or CycleScopeCache(user, db)
    excluded = 0

    requested: UUID | None = None
    if requested_project_id:
        # 显式指定项目：走既有守卫（含 RLS context 设置与越权审计）
        await ownership_guard.assert_target_accessible(user=user, project_id=requested_project_id, db=db)
        requested = _to_uuid(requested_project_id)
        if requested is None or not await _live_project_ids(db, (requested,)):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "FORBIDDEN_PROJECT", "message": "目标项目不存在或已删除，拒绝访问"},
            )
        if await _cycle_scoped(user, (requested,), cache):
            raise HTTPException(
                status_code=403,
                detail={"error_code": CYCLE_SCOPED_PROJECT, "message": CYCLE_SCOPED_PROJECT_MESSAGE},
            )
        project_ids: frozenset[UUID] | None = frozenset({requested})
    else:
        accessible = await ownership_guard.get_accessible_project_ids(user, db)
        if accessible is None:
            warnings.append(ALL_PROJECTS_WARNING)
            project_ids = None
        else:
            live = await _live_project_ids(db, accessible)
            # 对本人设有循环范围的项目排除出作用域（fail-closed）：构建器按表取数，无法与试算表页同口径按循环过滤
            restricted = await _cycle_scoped(user, live, cache)
            excluded = len(restricted)
            project_ids = live - restricted
            if excluded:
                warnings.append(cycle_excluded_warning(excluded))
            elif not project_ids:
                warnings.append(EMPTY_SCOPE_WARNING)

    return BuilderScope(
        project_ids=project_ids,
        unscoped_tables=unscoped,
        warnings=tuple(warnings),
        requested_project_id=requested,
        dataset_predicates=await _dataset_predicates(db, tables, project_ids, year),
        excluded_cycle_scoped=excluded,
    )


def _to_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _live_projects_subquery() -> Select:
    """「全部未删除项目」的 id 子查询（不随外层的 ``projects`` 自动关联）。"""
    projects = Project.__table__
    return select(projects.c.id).where(projects.c.is_deleted == false()).correlate(None)


def scope_predicates(table_name: str, scope: BuilderScope, *, year: int | None = None) -> list[ColumnElement]:
    """计划中一张表（基表或 JOIN 目标）的作用域谓词（ADR-AQL-09）。

    项目（``projects`` 按 ``id``；不限项目时其余表为 ``project_id IN (未删除项目)``）、``is_deleted = false``（有列时）、
    四表生效数据集口径、请求年度（有 ``year`` 列且请求带年度）、报表配置的项目副本行只含可访问项目（不限项目时不加）。
    """
    table = _table(table_name)
    if table is None:
        return []
    predicates: list[ColumnElement] = []
    project_col = _project_column(table_name)
    if project_col is not None:
        if not scope.is_all_projects:
            predicates.append(project_col.in_(sorted(scope.project_ids or (), key=str)))
        elif table_name != "projects":
            predicates.append(project_col.in_(_live_projects_subquery()))
    if "is_deleted" in table.c:
        predicates.append(table.c.is_deleted == false())
    dataset = scope.dataset_predicates.get(table_name)
    if dataset is not None:
        predicates.append(dataset)
    if year is not None and "year" in table.c:
        predicates.append(table.c.year == year)
    if table_name in GLOBAL_CONFIG_TABLES and not scope.is_all_projects:
        column = table.c.applicable_standard
        copies = [f"{PROJECT_COPY_PREFIX}{pid}" for pid in sorted(scope.project_ids or (), key=str)]
        predicates.append(or_(column.notlike(f"{PROJECT_COPY_PREFIX}%"), column.in_(copies)))
    return predicates


def apply_scope_to_select(
    stmt: Select, *, scope: BuilderScope, table_name: str, year: int | None = None
) -> Select:
    """把基表的作用域谓词追加到 ``SELECT``（R2.1）。

    调用点必须是 WHERE 组装的**最后一步**：追加而非合并，用户 DSL 里即便自己写了 ``project_id`` 过滤也只会与本约束
    取交集，无法放宽（AND 语义）。JOIN 目标表的谓词不走这里，见 ``builder_dsl._build_select``（并入 ON）。
    """
    predicates = scope_predicates(table_name, scope, year=year)
    return stmt.where(*predicates) if predicates else stmt


def scope_signature(scope: BuilderScope) -> str:
    """作用域的稳定签名，纳入缓存键（R2.4）。

    改造前缓存键写死 ``project_id="__query_builder__"`` —— 两个可访问项目集合不同
    的用户对同一 DSL 会命中同一条缓存，等于跨作用域泄漏。
    """
    if scope.is_all_projects:
        return "all"
    joined = ",".join(sorted(str(pid) for pid in (scope.project_ids or ())))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]
