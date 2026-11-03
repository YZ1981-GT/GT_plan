"""撤销抽凭的鉴权与阶段规则（spec voucher-identity-writeback-and-audit-phase 任务 9，ADR-VK-08，需求 6.3）

撤销之后宿主会按批次删底稿行，所以撤销端点不能只校验登录。SQLite 真 ORM 行 + 端点级请求，
真实的 authorize_wp_edit 与项目阶段判定都跑：
- 本项目编辑成员撤销最近一次年审批次 → 200，记录标撤销并回报批次号；
- 别的项目的记录按不存在处理（404），记录不动；只读成员、非成员 → 403；
- 项目在年审阶段时撤销预审批次 → 409 PRELIMINARY_BATCH_LOCKED，记录不动；预审阶段可撤销预审批次。
"""
from __future__ import annotations

import uuid

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType, WpStatus

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

EDITOR, READER, STRANGER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PROJECT, OTHER = uuid.uuid4(), uuid.uuid4()
WP, OTHER_WP = uuid.uuid4(), uuid.uuid4()


def _log(project_id, wp_id, phase: str) -> WorkpaperExtractionLog:
    return WorkpaperExtractionLog(
        id=uuid.uuid4(), project_id=project_id, workpaper_id=wp_id, user_id=EDITOR,
        extraction_type="voucher_sampling", extraction_criteria={"phase": phase},
        total_matched=3, filled_count=1, fill_mode="append", is_undone=False,
        batch_id=uuid.uuid4(), status="active",
    )


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, name in ((EDITOR, "editor"), (READER, "reader"), (STRANGER, "stranger")):
            session.add(User(id=uid, username=name, email=f"{name}@test.com", hashed_password="x", role="auditor"))
        for pid, wp_id, name in ((PROJECT, WP, "撤销鉴权"), (OTHER, OTHER_WP, "别的项目")):
            session.add(Project(id=pid, name=name, client_name="测试", project_type=ProjectType.annual,
                                status=ProjectStatus.execution, created_by=EDITOR, audit_year=2025))
            idx = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code="D2", wp_name="营业收入", audit_cycle="D",
                          status=WpStatus.not_started)
            session.add(idx)
            session.add(WorkingPaper(id=wp_id, project_id=pid, wp_index_id=idx.id, file_path="x.xlsx",
                                     source_type=WpSourceType.template, file_version=1))
            session.add(ProjectUser(project_id=pid, user_id=EDITOR, role="auditor", permission_level="edit",
                                    is_deleted=False))
        session.add(ProjectUser(project_id=PROJECT, user_id=READER, role="auditor", permission_level="readonly",
                                is_deleted=False))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import voucher_sampling

    app = FastAPI()
    app.include_router(voucher_sampling.router)
    state = {"user": EDITOR}

    class _User:
        def __init__(self, uid):
            self.id = uid
            self.username = "u"

        class _Role:
            value = "auditor"

        role = _Role()

    async def _db():
        yield db

    async def _user():
        return _User(state["user"])

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


async def _add(db, *rows):
    db.add_all(rows)
    await db.commit()
    return rows


async def _set_phase(db, pid, phase: str):
    await db.execute(sa.update(Project).where(Project.id == pid).values(current_audit_phase=phase))
    await db.commit()


async def _undone(db, log_id) -> bool:
    db.expire_all()
    return bool((await db.execute(sa.select(WorkpaperExtractionLog.is_undone)
                                  .where(WorkpaperExtractionLog.id == log_id))).scalar_one())


def _undo(client, pid, log_id):
    return client.post(f"/api/projects/{pid}/sampling/voucher-undo", params={"log_id": str(log_id)})


async def test_editor_undoes_latest_final_batch_and_gets_batch_id(client, db):
    (log,) = await _add(db, _log(PROJECT, WP, "final"))
    resp = await _undo(client, PROJECT, log.id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["batch_id"] == str(log.batch_id)
    assert await _undone(db, log.id)


async def test_other_projects_log_is_not_found_and_untouched(client, db):
    (log,) = await _add(db, _log(OTHER, OTHER_WP, "final"))
    resp = await _undo(client, PROJECT, log.id)  # 记录属于别的项目，却从本项目的 URL 撤销
    assert resp.status_code == 404
    assert not await _undone(db, log.id)


async def test_readonly_member_and_stranger_are_forbidden(client, db):
    (log,) = await _add(db, _log(PROJECT, WP, "final"))
    for uid in (READER, STRANGER):
        client.as_user(uid)
        assert (await _undo(client, PROJECT, log.id)).status_code == 403
    assert not await _undone(db, log.id)


async def test_preliminary_batch_is_locked_in_final_phase(client, db):
    await _set_phase(db, PROJECT, "final")
    (log,) = await _add(db, _log(PROJECT, WP, "preliminary"))
    resp = await _undo(client, PROJECT, log.id)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "PRELIMINARY_BATCH_LOCKED"
    assert not await _undone(db, log.id)


async def test_preliminary_batch_can_be_undone_in_preliminary_phase(client, db):
    await _set_phase(db, PROJECT, "preliminary")
    (log,) = await _add(db, _log(PROJECT, WP, "preliminary"))
    resp = await _undo(client, PROJECT, log.id)
    assert resp.status_code == 200, resp.text
    assert await _undone(db, log.id)
