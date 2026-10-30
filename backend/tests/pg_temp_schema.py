"""在随机 PostgreSQL schema 里跑真实迁移 SQL 的测试辅助（V218 / V225 等迁移契约测试共用）。

只在临时 schema 里建表 / 跑迁移，finally 删 schema 并核对已删除；共享 public 一律只读。
迁移 SQL 一律经 ``MigrationRunner._split_sql_statements`` 拆句执行（与生产同一拆句器）。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND / "migrations"


def postgres_settings():
    from app.core.config import settings

    if make_url(settings.DATABASE_URL).get_backend_name() != "postgresql":
        pytest.skip("真实迁移测试需要 PostgreSQL")
    return settings


@asynccontextmanager
async def temporary_schema(prefix: str) -> AsyncIterator[tuple[AsyncEngine, str]]:
    """建随机 schema，产出 search_path 只含该 schema 的引擎；退出时删 schema（含失败路径）。"""
    settings = postgres_settings()
    connect_args = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    admin_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=connect_args)
    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    scoped_engine: AsyncEngine | None = None
    try:
        async with admin_engine.begin() as admin:
            await admin.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped_engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**connect_args, "server_settings": {"search_path": schema}},
        )
        async with scoped_engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT current_schema()")) == schema
            assert await conn.scalar(sa.text("SHOW search_path")) == schema
        yield scoped_engine, schema
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        try:
            async with admin_engine.begin() as admin:
                await admin.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                remaining = await admin.scalar(
                    sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :schema"), {"schema": schema})
                assert remaining == 0
        finally:
            await admin_engine.dispose()


def split_sql(path: Path) -> list[str]:
    from app.core.migration_runner import MigrationRunner

    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    assert statements, f"{path.name} 未拆出可执行 SQL"
    return statements


async def run_sql_file(conn: AsyncConnection, path: Path) -> int:
    statements = split_sql(path)
    for statement in statements:
        await conn.exec_driver_sql(statement)
    return len(statements)


async def table_names(conn: AsyncConnection) -> set[str]:
    rows = await conn.execute(sa.text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
    """))
    return {row[0] for row in rows}


async def constraint_names(conn: AsyncConnection, table: str) -> set[str]:
    rows = await conn.execute(sa.text("""
        SELECT c.conname
        FROM pg_constraint AS c
        JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS ns ON ns.oid = t.relnamespace
        WHERE ns.nspname = current_schema() AND t.relname = :table
    """), {"table": table})
    return {row[0] for row in rows}


def sqlstate(exc: sa.exc.DBAPIError) -> str | None:
    for candidate in (exc.orig, getattr(exc.orig, "__cause__", None)):
        state = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if state:
            return str(state)
    return None


#: V225（原 V217，标识符沿用 V217_*）/ V218 需要的最小父表（V225 只用 procedure_instances；V218 回填读预览凭证、外键指向项目 / 用户）。
V217_PARENT_DDL = (
    "CREATE TABLE projects (id UUID PRIMARY KEY)",
    "CREATE TABLE users (id UUID PRIMARY KEY)",
    """
    CREATE TABLE procedure_instances (
        id UUID PRIMARY KEY,
        project_id UUID NOT NULL,
        audit_cycle VARCHAR(10) NOT NULL,
        procedure_code VARCHAR(50) NOT NULL,
        wp_code VARCHAR(50),
        is_deleted BOOLEAN NOT NULL DEFAULT false
    )
    """,
    """
    CREATE TABLE procedure_operation_previews (
        id UUID PRIMARY KEY,
        actor_user_id UUID NOT NULL REFERENCES users(id),
        project_id UUID NOT NULL REFERENCES projects(id),
        operation VARCHAR(40) NOT NULL,
        request_payload_snapshot JSONB NOT NULL DEFAULT '{}',
        consumed_at TIMESTAMPTZ,
        consumed_request_id VARCHAR(80)
    )
    """,
)
V217_PARENT_TABLES = {"projects", "users", "procedure_instances", "procedure_operation_previews"}


async def create_v217_parents(conn: AsyncConnection) -> None:
    for ddl in V217_PARENT_DDL:
        await conn.exec_driver_sql(ddl)
