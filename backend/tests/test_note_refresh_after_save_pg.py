"""真库：底稿保存事件不再改写附注（PG）。

历史：`build_and_sync` 无触发人时写 `User(id=UUID(int=0))` 撞 `disclosure_notes_updated_by_fkey`（spec
writeback-followup-issue-closure R7.2，这条外键只有 PG 有）。2026-10-26 起后端披露表 builder 不接任何写路径（与前端
口径不一，spec note-pull-header-formula-closure R1），2026-10-27 连模块一起删除（spec note-pull-followup-closure R17）
⇒ 原先针对 builder 身份 / 保存点的用例随模块删除；保存事件 handler 改为只读诊断，这里钉住它在真库上不建附注、不写身份。
每个用例在一个最终回滚的事务里建数据，不落库。
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.note_disclosure_refresh_service import handle_workpaper_saved, refresh_note_from_disclosure
from tests.procedure_delegation_visibility._factories import mk_project, mk_user, mk_working_paper, mk_wp_index

IS_PG = settings.DATABASE_URL.startswith("postgresql")
pytestmark = [pytest.mark.pg_only, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

YEAR = 2025
WP_CODE = "D3"


@pytest_asyncio.fixture
async def pg_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


async def _saved_workpaper(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """【测试】项目 + D3 底稿 + 一条审定数。"""
    project = await mk_project(session)
    index = await mk_wp_index(session, project.id, wp_code=WP_CODE, audit_cycle="D")
    paper = await mk_working_paper(session, project.id, index.id)
    await session.execute(
        sa.text("INSERT INTO checklist_responses (project_id, wp_id, item_id, remark) VALUES (:p, :w, :i, :r)"),
        {"p": project.id, "w": paper.id, "i": f"{WP_CODE}-adj-tb-amount", "r": "12345.67"},
    )
    await session.flush()
    return project.id, paper.id


async def _note_rows(session: AsyncSession, project_id: uuid.UUID) -> list[sa.Row]:
    return list((await session.execute(
        sa.text(
            "SELECT note_section, updated_by, last_sync_user_id, last_sync_wp_id FROM disclosure_notes "
            "WHERE project_id = :p AND year = :y AND NOT is_deleted"
        ),
        {"p": project_id, "y": YEAR},
    )).fetchall())


async def test_save_event_handler_is_read_only(pg_session, monkeypatch):
    """底稿保存 handler 只读诊断：不建附注、不改标记、不写身份。"""
    project_id, paper_id = await _saved_workpaper(pg_session)
    saver = await mk_user(pg_session)

    @contextlib.asynccontextmanager
    async def _shared_session():
        yield pg_session

    monkeypatch.setattr("app.core.database.async_session", lambda: _shared_session())
    extra = {"wp_code": WP_CODE, "wp_id": str(paper_id), "trigger": "checklist_response_save", "user_id": str(saver.id)}
    outcome = await handle_workpaper_saved(
        EventPayload(event_type=EventType.WORKPAPER_SAVED, project_id=project_id, year=YEAR, extra=extra)
    )
    assert outcome["status"] == "ok", outcome
    assert outcome["synced"] == 0
    assert await _note_rows(pg_session, project_id) == [], "只读：不再把 builder 的错数写成附注"


async def test_status_query_on_unsynced_section_keeps_the_transaction_healthy(pg_session):
    """状态查询（refresh-from-disclosure 用）在没有附注的项目上只回 not_found，PG 事务仍健康。"""
    project_id, _ = await _saved_workpaper(pg_session)
    result = await refresh_note_from_disclosure(pg_session, project_id, YEAR, WP_CODE)
    assert result is not None
    assert (await pg_session.execute(sa.text("SELECT 1"))).scalar_one() == 1
    assert await _note_rows(pg_session, project_id) == []
