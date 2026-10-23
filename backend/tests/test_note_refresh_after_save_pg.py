"""真库复现：底稿保存触发的附注刷新不再因占位身份撞外键（spec writeback-followup-issue-closure R7.2）。

修前 `build_and_sync` 无触发人时写 `User(id=UUID(int=0))`、底稿写 `UUID(int=0)`；而底稿保存的事件从来不带
user_id ⇒ 每次都在下一条查询的 autoflush 上撞 `disclosure_notes_updated_by_fkey`，整次附注刷新失败
（日志 `note_disclosure_refresh: handler failed … Query-invoked autoflush`）。这条外键只有 PG 有，SQLite 证明不了。

判据：无触发人 ⇒ `updated_by` 记 NULL（系统重算）、刷新照常完成；有触发人 ⇒ 记真实保存人；`last_sync_wp_id`
是真实底稿；builder 失败只回滚自己的保存点，随后的刷新仍在健康事务上；保存事件 → handler 端到端返回 ok。
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
from app.services.disclosure_payload_builder_service import build_and_sync
from app.services.note_disclosure_refresh_service import handle_workpaper_saved, refresh_note_from_disclosure
from tests.procedure_delegation_visibility._factories import mk_project, mk_user, mk_working_paper, mk_wp_index

IS_PG = settings.DATABASE_URL.startswith("postgresql")
pytestmark = [pytest.mark.pg_only, pytest.mark.skipif(not IS_PG, reason="need PostgreSQL")]

YEAR = 2025
WP_CODE = "D3"  # 标准 builder（预收款项），读 `D3-adj-tb-amount`


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
    """【测试】项目 + D3 底稿 + 一条审定数（builder 的数据源）。"""
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


async def test_save_without_user_is_a_system_recompute_not_a_foreign_key_error(pg_session):
    project_id, paper_id = await _saved_workpaper(pg_session)
    synced = await build_and_sync(pg_session, project_id, YEAR, WP_CODE)
    assert not synced.get("skipped"), synced
    # 修前正是这一步的查询触发 autoflush、撞 disclosure_notes_updated_by_fkey
    await refresh_note_from_disclosure(pg_session, project_id, YEAR, WP_CODE)
    rows = await _note_rows(pg_session, project_id)
    assert [r.note_section for r in rows] == [synced["section_id"]]
    assert rows[0].updated_by is None and rows[0].last_sync_user_id is None, "无触发人 = 系统重算，不编身份"
    assert rows[0].last_sync_wp_id == paper_id, "来源是 builder 读的那张底稿，不是全零 UUID"


async def test_save_with_user_records_the_saver(pg_session):
    project_id, paper_id = await _saved_workpaper(pg_session)
    saver = await mk_user(pg_session)
    synced = await build_and_sync(pg_session, project_id, YEAR, WP_CODE, triggered_by=saver.id)
    assert not synced.get("skipped"), synced
    rows = await _note_rows(pg_session, project_id)
    assert (rows[0].updated_by, rows[0].last_sync_user_id, rows[0].last_sync_wp_id) == (saver.id, saver.id, paper_id)


async def test_builder_failure_only_rolls_back_its_own_savepoint(pg_session, monkeypatch):
    project_id, _ = await _saved_workpaper(pg_session)
    import app.services.wp_disclosure_sync_service as sync_mod

    async def _failing_sync(db, *_a, **_k):
        await db.execute(sa.text("SELECT 1 / 0"))  # PG 上这一下就让事务进 aborted

    monkeypatch.setattr(sync_mod, "sync_from_workpaper", _failing_sync)
    with pytest.raises(sa.exc.DBAPIError):
        await build_and_sync(pg_session, project_id, YEAR, WP_CODE)
    # 吞掉异常而不回滚到保存点 ⇒ 这里 InFailedSQLTransaction；现在事务仍健康，刷新照常
    assert (await pg_session.execute(sa.text("SELECT 1"))).scalar_one() == 1
    await refresh_note_from_disclosure(pg_session, project_id, YEAR, WP_CODE)


async def test_constraint_error_at_flush_rolls_back_only_the_savepoint(pg_session, monkeypatch):
    """约束错误要到 flush 才暴露（正是修前的形态）：同样只回滚 builder 的保存点。"""
    project_id, _ = await _saved_workpaper(pg_session)
    taken = await mk_user(pg_session)
    import app.services.wp_disclosure_sync_service as sync_mod
    from app.models.core import User, UserRole

    async def _sync_with_bad_write(db, *_a, **_k):
        db.add(User(username=taken.username, email=f"{uuid.uuid4().hex}@t.example",
                    hashed_password="x", role=UserRole("auditor"), is_active=True))
        return {}

    monkeypatch.setattr(sync_mod, "sync_from_workpaper", _sync_with_bad_write)
    with pytest.raises(sa.exc.IntegrityError):
        await build_and_sync(pg_session, project_id, YEAR, WP_CODE)
    assert (await pg_session.execute(sa.text("SELECT 1"))).scalar_one() == 1
    await refresh_note_from_disclosure(pg_session, project_id, YEAR, WP_CODE)


async def test_query_failure_swallowed_inside_the_builder_does_not_poison_the_refresh(pg_session, monkeypatch):
    """builder 自己吞掉查询失败、只回「无数据」：PG 上事务已 aborted，跳过路径也必须回滚到保存点。"""
    project_id, _ = await _saved_workpaper(pg_session)
    import app.services.disclosure_builders.standard_builder as std

    async def _failing_load(db, *_a, **_k):
        await db.execute(sa.text("SELECT 1 / 0"))

    monkeypatch.setattr(std, "load_disclosure_entries", _failing_load)
    assert (await build_and_sync(pg_session, project_id, YEAR, WP_CODE)).get("skipped") is True
    assert (await pg_session.execute(sa.text("SELECT 1"))).scalar_one() == 1


@pytest.mark.parametrize("identity", ["saver", "absent", "malformed"])
async def test_save_event_handler_end_to_end(pg_session, monkeypatch, identity):
    project_id, paper_id = await _saved_workpaper(pg_session)
    saver = await mk_user(pg_session)

    @contextlib.asynccontextmanager
    async def _shared_session():
        yield pg_session  # handler 的 commit 在 create_savepoint 下只释放保存点

    monkeypatch.setattr("app.core.database.async_session", lambda: _shared_session())
    extra = {"wp_code": WP_CODE, "wp_id": str(paper_id), "trigger": "checklist_response_save"}
    if identity != "absent":
        extra["user_id"] = str(saver.id) if identity == "saver" else "not-a-uuid"
    outcome = await handle_workpaper_saved(
        EventPayload(event_type=EventType.WORKPAPER_SAVED, project_id=project_id, year=YEAR, extra=extra)
    )
    assert outcome["status"] == "ok", outcome
    rows = await _note_rows(pg_session, project_id)
    assert len(rows) == 1
    assert rows[0].updated_by == (saver.id if identity == "saver" else None)
    assert rows[0].last_sync_wp_id == paper_id
