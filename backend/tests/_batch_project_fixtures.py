"""批量建项 hardening 测试共用的隔离 SQLite engine / session fixtures。

相关三个测试文件已入库，但本插件曾漏提交，干净检出会在 pytest 收集期报
``ModuleNotFoundError: tests._batch_project_fixtures``。
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 — 注册平台 ORM
import app.models.project_creation_grant_models  # noqa: F401 — 注册 V233 授权表
from app.models.base import Base

# PostgreSQL 专用类型在 SQLite 测试中的最小编译映射；与既有批量建项测试口径一致。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest_asyncio.fixture
async def db(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
