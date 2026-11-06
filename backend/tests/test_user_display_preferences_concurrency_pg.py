"""账号显示偏好首写竞争的真实 PostgreSQL 判据。

仅在 DATABASE_URL 明确指向 PostgreSQL 时运行。每例创建并删除独立 schema，
不读写 public 或共享业务表。

Validates: Requirements R2 / AC-03、AC-24；design §16 F7。
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.base import Base, UserRole
from app.models.core import User
from app.models.user_display_preferences import UserDisplayPreferences
from app.schemas.display_preferences import DisplayPreferencesPatch
from app.services.user_display_preferences_service import (
    DisplayPrefsRevisionConflict,
    patch_preferences,
)

pytestmark = pytest.mark.pg_only
_TABLES = (User.__table__, UserDisplayPreferences.__table__)


def _engine(*, schema: str | None = None):
    from app.core.config import settings

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgres"):
        raise RuntimeError("显示偏好并发判据必须显式使用 PostgreSQL DATABASE_URL")
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    if schema is not None:
        connect_args["server_settings"] = {"search_path": schema}
    return create_async_engine(database_url, poolclass=NullPool, connect_args=connect_args)


@pytest.mark.asyncio
async def test_two_first_writes_produce_one_success_and_one_current_conflict():
    """后到者必须等待提交，再从已回滚的 SAVEPOINT 外读到获胜行。"""

    if os.environ.get("GT_DISPLAY_PREFS_PG_CONCURRENCY") != "1":
        pytest.skip("需要显式 GT_DISPLAY_PREFS_PG_CONCURRENCY=1 的可用 PostgreSQL 连接")

    schema = f"gds_display_prefs_{uuid4().hex[:12]}"
    user_id = uuid4()
    admin = _engine()
    scoped = None
    release_first = asyncio.Event()
    first_flushed = asyncio.Event()
    second_started = asyncio.Event()
    try:
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        scoped = _engine(schema=schema)
        async with scoped.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=_TABLES,
                )
            )
        sessions = async_sessionmaker(scoped, expire_on_commit=False)
        async with sessions() as db:
            db.add(User(
                id=user_id,
                username=f"gds-race-{user_id.hex[:10]}",
                email=f"gds-race-{user_id.hex[:10]}@test.invalid",
                hashed_password="test-only",
                role=UserRole.auditor,
            ))
            await db.commit()

        async def first_writer():
            async with sessions() as db:
                result, _ = await patch_preferences(
                    db,
                    user_id,
                    DisplayPreferencesPatch(base_revision=0, font_size="lg"),
                )
                first_flushed.set()
                await release_first.wait()
                await db.commit()
                return result

        async def second_writer():
            await first_flushed.wait()
            second_started.set()
            async with sessions() as db:
                try:
                    await patch_preferences(
                        db,
                        user_id,
                        DisplayPreferencesPatch(base_revision=0, font_size="xs"),
                    )
                except DisplayPrefsRevisionConflict as exc:
                    await db.rollback()
                    return exc.current
                await db.commit()
                raise AssertionError("并发首写错误地同时成功")

        first_task = asyncio.create_task(first_writer())
        await first_flushed.wait()
        second_task = asyncio.create_task(second_writer())
        await second_started.wait()
        await asyncio.sleep(0.1)
        assert not second_task.done(), "第二个首写没有等待唯一键竞争的获胜事务"
        release_first.set()

        first = await asyncio.wait_for(first_task, timeout=5)
        current = await asyncio.wait_for(second_task, timeout=5)
        assert first.revision == current.revision == 1
        assert first.font_size == current.font_size == "lg"

        async with sessions() as db:
            rows = (await db.execute(select(UserDisplayPreferences))).scalars().all()
        assert len(rows) == 1
        assert rows[0].revision == 1 and rows[0].font_size == "lg"
    finally:
        release_first.set()
        if scoped is not None:
            await scoped.dispose()
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()
