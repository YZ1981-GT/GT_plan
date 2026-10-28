"""ORM 的 ``server_default`` 不得带 PG 字面类型转换（``'[]'::jsonb`` 等）。

真表由 ``backend/migrations/V*.sql`` 建，ORM 的 ``server_default`` 只在 SQLite 测试 ``create_all`` 时进 DDL；
SQLite 解析不了 ``::``，整批建表报 "unrecognized token" ⇒ 所有建全量表的 SQLite 用例一起挂。模型里已有 5 处注释写明
这条约定，2026-10-25 新加的 ``consol_note_template_push_log`` 仍写了 ``'[]'::jsonb``（回收站 / WOPI 回滚等用例全挂），
故改成守卫（spec procedure-chain-followup-closure 实施中发现）。
"""
from __future__ import annotations

import importlib
import pkgutil

import app.models
from app.models.base import Base

for _module in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_module.name)


def test_no_pg_cast_in_server_defaults():
    offenders = sorted(
        f"{table.name}.{column.name}: {column.server_default.arg}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.server_default is not None and "::" in str(getattr(column.server_default, "arg", ""))
    )
    assert offenders == [], "server_default 改写成双方言字面量（如 '[]' / '{}'）：\n" + "\n".join(offenders)


def test_guard_sees_server_defaults():
    """反向自检：确有大量 server_default 被扫到（判据抽不到值时上面那条会空转变绿）。"""
    with_default = [c for t in Base.metadata.tables.values() for c in t.columns if c.server_default is not None]
    assert len(with_default) > 100
