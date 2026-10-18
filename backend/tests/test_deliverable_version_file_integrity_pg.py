"""交付件版本完整性真实 PG 守卫（只读 + 行锁，事务均 rollback）。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.phase13_models import WordExportTaskVersion
from app.routers.deliverable import _verified_version_path
from app.services.deliverable_service import DeliverableService

pytestmark = pytest.mark.pg_only

TASK_ID = UUID("f2238a0d-f52d-4762-aeb1-9b8e3ec3a01f")


@asynccontextmanager
async def _pg_session():
    """每个 pytest 事件循环自建 NullPool 引擎，避免全局 asyncpg 连接跨 loop 复用。"""
    engine = create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            yield db
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_historical_shared_paths_fail_closed_instead_of_serving_wrong_bytes():
    """真库基线：19 条共享路径版本中 16 条已被覆盖 ⇒ 409；最新的 3 条指纹一致 ⇒ 可下载。"""
    async with _pg_session() as db:
        try:
            duplicated_paths = sa.select(WordExportTaskVersion.file_path).where(
                WordExportTaskVersion.file_path.is_not(None)
            ).group_by(
                WordExportTaskVersion.word_export_task_id, WordExportTaskVersion.file_path
            ).having(sa.func.count() > 1)
            versions = list((await db.execute(
                sa.select(WordExportTaskVersion)
                .where(WordExportTaskVersion.file_path.in_(duplicated_paths))
                .order_by(WordExportTaskVersion.word_export_task_id, WordExportTaskVersion.version_no)
            )).scalars())
            ok = conflict = 0
            for version in versions:
                try:
                    _verified_version_path(version)
                    ok += 1
                except HTTPException as exc:
                    assert exc.status_code == 409 and "后续生成覆盖" in str(exc.detail)
                    conflict += 1
            assert (len(versions), conflict, ok) == (19, 16, 3)
        finally:
            await db.rollback()


@pytest.mark.asyncio
async def test_task_row_for_update_serializes_version_allocation():
    """A 持有 task 行锁时，B 的同一锁在 100ms 内超时；证明锁不是注释 / 普通 SELECT。"""
    async with _pg_session() as db_a, _pg_session() as db_b:
        try:
            locked = await DeliverableService(db_a)._lock_task(TASK_ID)
            assert locked is not None
            await db_b.execute(sa.text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(DBAPIError, match="lock timeout|canceling statement"):
                await DeliverableService(db_b)._lock_task(TASK_ID)
        finally:
            await db_a.rollback()
            await db_b.rollback()


@pytest.mark.asyncio
async def test_live_unique_index_exists_and_no_duplicate_version_numbers():
    async with _pg_session() as db:
        try:
            index = (await db.execute(sa.text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND indexname='uq_word_export_versions_task_no'"
            ))).scalar_one_or_none()
            assert index and "UNIQUE INDEX" in index
            duplicate = (await db.execute(sa.text(
                "SELECT count(*) FROM (SELECT 1 FROM word_export_task_versions "
                "GROUP BY word_export_task_id, version_no HAVING count(*) > 1) d"
            ))).scalar_one()
            assert duplicate == 0
        finally:
            await db.rollback()
