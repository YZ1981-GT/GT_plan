"""知识库真库守卫共享夹具：真实 PostgreSQL 上的一次性 scratch schema。

spec: knowledge-base-retrieval-and-authz-closure（design §9.2）

沿用 ``test_knowledge_delete_hook_isolation_pg.py`` 的做法：
  * 表由 **ORM metadata** 派生（同列同类型；去外键、去索引、去 ``embedding_vec`` ——
    与未装 pgvector 的真库一致），禁止手抄 DDL；
  * 独立引擎 ``search_path`` 只含 scratch schema，与业务库零交叉；
  * 结束时 ``DROP SCHEMA ... CASCADE`` 放在 ``finally``，清理失败记入 errors 让守卫红；
  * ``DATABASE_URL`` 非 PostgreSQL 直接报错（判据依赖 PG 事务语义，不 skip）。
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import sqlalchemy as sa

os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 与未安装 pgvector 的真库一致：V119 在扩展缺失时跳过该列
ABSENT_COLUMNS: dict[str, set[str]] = {"knowledge_index": {"embedding_vec"}}


class HarnessError(RuntimeError):
    """夹具自身失败（禁 fail-open：守卫必须红，而不是降级成『无数据』）。"""


def _scratch_type(column: sa.Column):
    from sqlalchemy.dialects import postgresql

    t = column.type
    if isinstance(t, sa.Enum) and t.name:
        return postgresql.ENUM(*t.enums, name=t.name, create_type=False)
    return t


def fk_free_copy(table: sa.Table) -> sa.Table:
    absent = ABSENT_COLUMNS.get(table.name, set())
    return sa.Table(
        table.name,
        sa.MetaData(),
        *[
            sa.Column(
                column.name,
                _scratch_type(column),
                primary_key=column.primary_key,
                nullable=column.nullable,
                server_default=column.server_default,
            )
            for column in table.columns
            if column.name not in absent
        ],
    )


def enum_ddl(tables: list[sa.Table]) -> list[str]:
    seen: dict[str, list[str]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                seen.setdefault(column.type.name, list(column.type.enums))
    return [
        "CREATE TYPE {name} AS ENUM ({labels})".format(
            name=name, labels=", ".join(f"'{label}'" for label in labels)
        )
        for name, labels in sorted(seen.items())
    ]


def knowledge_tables() -> list[sa.Table]:
    from app.models.ai_models import KnowledgeIndex
    from app.models.core import ProjectUser
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder

    return [
        KnowledgeFolder.__table__,
        KnowledgeDocument.__table__,
        KnowledgeIndex.__table__,
        ProjectUser.__table__,
    ]


def migration_statement(filename: str, marker: str) -> str:
    """从真实迁移文件里取出包含 ``marker`` 的那条语句（去掉注释行）。

    唯一索引 / 部分索引在 ORM 上没有声明（由迁移拥有），scratch 表不会自带；
    直接执行迁移文件里的原句，保证测试验证的是**真实迁移**的索引定义，而不是手抄一份。
    """
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "migrations" / filename
    text = path.read_bytes().decode("utf-8")
    body = "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("--"))
    hits = [s.strip() for s in body.split(";") if marker in s]
    if len(hits) != 1:
        raise HarnessError(f"{filename} 中含 {marker!r} 的语句应恰好 1 条，实际 {len(hits)}")
    return hits[0]


@asynccontextmanager
async def scratch_schema(
    prefix: str,
    errors: list[str],
    *,
    extra_tables: list[sa.Table] | tuple[sa.Table, ...] = (),
    extra_ddl: list[str] | tuple[str, ...] = (),
) -> AsyncIterator[Any]:
    """建 scratch schema + 知识库相关表（及 ``extra_tables``），执行 ``extra_ddl``，
    yield ``async_sessionmaker``；退出时整库删除。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise HarnessError(
            "本守卫依赖 PostgreSQL 事务 / SAVEPOINT 语义，必须真实 PostgreSQL；"
            f"当前 DATABASE_URL={settings.DATABASE_URL!r}"
        )
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    schema = f"tmp_{prefix}_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        base_tables = knowledge_tables()
        tables = base_tables + [t for t in extra_tables if all(t is not b for b in base_tables)]
        async with engine.begin() as conn:
            for ddl in enum_ddl(tables):
                await conn.exec_driver_sql(ddl)
            for table in tables:
                await conn.run_sync(fk_free_copy(table).create)
            for ddl in extra_ddl:
                await conn.exec_driver_sql(ddl)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cleanup {schema}: {type(exc).__name__}: {exc}")
        await admin.dispose()
