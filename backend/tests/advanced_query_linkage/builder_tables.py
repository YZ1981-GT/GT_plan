"""构建器端点测试的建表清单：白名单表 + 它们的外键闭包（AQ-32；advanced-query-linkage-closure 任务 1）。

旧夹具 ``Base.metadata.create_all()`` 建全部 ORM 表：任一与构建器无关的模型带 PG 专用 ``server_default``（2026-10-26
实测是 ``consol_note_template_push_log.failures`` 的 ``'[]'::jsonb``），SQLite 建表即 ``unrecognized token ":"``，
``test_query_builder_endpoint.py`` 与 ``test_query_builder_joins.py`` 的 32 条用例全部在 setup 阶段报错 —— 构建器的
HTTP 行为在 HEAD 上没有一条能跑的测试。只建构建器白名单（``table_whitelist.TABLE_WHITELIST``）涉及的表及其外键
闭包，再加构建器作用域要读的成员表（``SCOPE_TABLES``）：不受无关模型影响，也不缺被引用的表；白名单增减表时清单随之
变化，不另维护第二份。

夹具建完表后用 ``assert_only_builder_tables`` 核对实际建出的表都在清单内（改回 ``create_all()`` 即红）。
"""
from __future__ import annotations

from sqlalchemy import Table, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.schema import sort_tables

from app.models.base import Base
from app.models.core import ProjectUser
from app.models.staff_models import ProjectAssignment
from app.services.custom_query.table_whitelist import TABLE_WHITELIST


def _foreign_key_closure(seeds: list[Table]) -> list[Table]:
    found: dict[str, Table] = {}
    stack = list(seeds)
    while stack:
        table = stack.pop()
        if table.name in found:
            continue
        found[table.name] = table
        stack.extend(fk.column.table for fk in table.foreign_keys)
    return list(found.values())


#: 构建器作用域读的成员表：``OwnershipGuard`` 的可访问项目集合 = project_users ∪ project_assignments（经 staff_members）。
#: 它们不在白名单里、也不被白名单表的外键引用，但非 admin / partner 角色的每次查询都要读。
SCOPE_TABLES: tuple[Table, ...] = (ProjectUser.__table__, ProjectAssignment.__table__)

#: 构建器白名单表 + 作用域成员表 + 它们的外键闭包，按外键依赖排序
BUILDER_TABLES: tuple[Table, ...] = tuple(sort_tables(_foreign_key_closure(
    [meta["model"].__table__ for meta in TABLE_WHITELIST.values()] + list(SCOPE_TABLES)
)))
BUILDER_TABLE_NAMES: frozenset[str] = frozenset(table.name for table in BUILDER_TABLES)


def create_builder_schema(conn: Connection) -> None:
    """只建 ``BUILDER_TABLES``（供 ``AsyncConnection.run_sync`` 调用）。"""
    Base.metadata.create_all(conn, tables=list(BUILDER_TABLES))


def create_tables_with_closure(conn: Connection, seeds: tuple[Table, ...]) -> None:
    """只建 ``seeds`` 及其外键闭包（业务视图注册表 / 数据集谓词的 SQLite 用例用；供 ``run_sync`` 调用）。"""
    Base.metadata.create_all(conn, tables=list(sort_tables(_foreign_key_closure(list(seeds)))))


async def assert_only_builder_tables(conn: AsyncConnection) -> None:
    """SQLite 库里实际建出的表都在 ``BUILDER_TABLE_NAMES`` 内，且白名单表一张不缺。"""
    created = set((await conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))).scalars())
    extra = sorted(created - BUILDER_TABLE_NAMES)
    assert not extra, f"夹具建了构建器白名单及其外键闭包以外的表（应只建 BUILDER_TABLES）：{extra[:10]}…共 {len(extra)} 张"
    missing = sorted({meta["model"].__table__.name for meta in TABLE_WHITELIST.values()} - created)
    assert not missing, f"构建器白名单表没有建出：{missing}"
