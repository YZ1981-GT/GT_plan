"""SQLite 用例开外键检查（spec procedure-chain-hardening-and-java-contracts R20）。

SQLite 默认不检查外键：插入顺序错（R3 模板复制：wp_index 与 working_paper 同一次 flush、先插了子表）、
引用不存在的行，在 SQLite 上照样通过，到 PG 才 500。涉及外键的用例建好引擎、**第一次连接之前**调这个
（StaticPool + ``:memory:`` 只在第一次连接时触发 connect 事件）。
"""
from __future__ import annotations

import sqlalchemy as sa


def enable_sqlite_foreign_keys(engine) -> None:
    """给 SQLite 引擎的每个新连接执行 ``PRAGMA foreign_keys=ON``（与 PG 一样检查外键）。"""

    @sa.event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def with_fk_parents(tables):
    """只建部分表的用例：补上这些表外键引用到的表（递归），否则开了外键检查后插入即报「no such table」。"""
    out, seen, stack = [], set(), list(tables)
    while stack:
        table = stack.pop()
        if table.name in seen:
            continue
        seen.add(table.name)
        out.append(table)
        stack.extend(fk.column.table for fk in table.foreign_keys)
    return out
