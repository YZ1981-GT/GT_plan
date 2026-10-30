"""确认 / 修订 AI 内容后写回附注的守卫（spec ai-chat-adopt-and-note-target-picker 复盘 P0）。

复盘发现的真缺陷（上一轮 confirm 写回的 6 条）在这里逐条钉死：
1. confirm/revise/reject 补项目级鉴权（之前只 get_current_user ⇒ 任意登录用户可写他项目附注）；
2. 附注写回走 DisclosureEngine.update_note（盖「最近一次编辑」），不裸改 text_content；
3. 编辑/合并锁不满足时**保持 pending**、返回原因，不假装已确认；
4. revise 也写修订文本（revised_content）；
5. 底稿类不自动写入；
6. 鉴权级别：确认=review，写附注=edit。

用真 ORM + 真 assert_project_permission + 真 DisclosureEngine.update_note（鉴权的
set_rls_context 对 SQLite 自动跳过）；每测试独立内存库，整体回滚不留库。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import app.models.core  # noqa: F401, E402
import app.models.audit_log_models  # noqa: F401, E402
import app.models.v3_refinement_models  # noqa: F401, E402
import app.models.report_models  # noqa: F401, E402

from app.models.base import Base  # noqa: E402

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["project_users"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["ai_content_log"],
            Base.metadata.tables["disclosure_notes"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@asynccontextmanager
async def _client(session, user):
    """真实 ai_content 路由；只替身 get_db / get_current_user，鉴权与写回走真实实现。"""
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.ai_content import router

    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest_asyncio.fixture
async def world(db_session):
    """项目 + 附注 + 三个成员（review / edit / 非成员）+ 一个 admin。"""
    from app.models.base import PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
    from app.models.core import Project, ProjectUser, User
    from app.models.report_models import DisclosureNote

    async def mk_user(role: UserRole) -> User:
        u = User(
            username=f"cw_{role.value}_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:10]}@cw.example",
            hashed_password="x", role=role, is_active=True,
        )
        db_session.add(u)
        await db_session.flush()
        return u

    project = Project(name=f"确认写回_{uuid.uuid4().hex[:6]}", client_name="客户",
                       status=ProjectStatus.execution, audit_year=2025)
    db_session.add(project)
    await db_session.flush()

    reviewer = await mk_user(UserRole.manager)      # review 级成员
    editor = await mk_user(UserRole.auditor)        # edit 级成员
    outsider = await mk_user(UserRole.auditor)      # 非本项目成员
    admin = await mk_user(UserRole.admin)

    db_session.add_all([
        ProjectUser(project_id=project.id, user_id=reviewer.id,
                    role=ProjectUserRole.manager, permission_level=PermissionLevel.review),
        ProjectUser(project_id=project.id, user_id=editor.id,
                    role=ProjectUserRole.auditor, permission_level=PermissionLevel.edit),
    ])
    note = DisclosureNote(
        project_id=project.id, year=2025, note_section="八、1",
        section_title="货币资金", section_id=f"sec_{uuid.uuid4().hex[:8]}",
        text_content="原有正文。", table_data={"rows": []},
    )
    db_session.add(note)
    await db_session.flush()
    await db_session.commit()

    return {
        "project": project, "note": note,
        "reviewer": reviewer, "editor": editor, "outsider": outsider, "admin": admin,
    }


async def _pending(db_session, project_id, *, target_cell, content="AI 起草的货币资金说明", user_id=None):
    from app.services import ai_content_log_service as svc

    log = await svc.create(
        db=db_session, project_id=project_id, user_id=user_id or uuid.uuid4(),
        instance_type="note", instance_id=uuid.uuid4(),
        target_cell=None, model="qwen3.5", prompt_hash=None,
        content_hash="c" * 64, generated_content=content, confidence=0.8,
    )
    # create() 会把 target_cell 前缀化；这里直接覆盖成测试需要的完整形态
    log.target_cell = target_cell
    await db_session.flush()
    await db_session.commit()
    return log


async def _note_text(db_session, note_id):
    from app.models.report_models import DisclosureNote

    return (await db_session.execute(
        sa.select(DisclosureNote.text_content).where(DisclosureNote.id == note_id)
    )).scalar_one()


async def _status(db_session, log_id):
    from app.models.v3_refinement_models import AiContentLog

    return (await db_session.execute(
        sa.select(AiContentLog.confirm_action).where(AiContentLog.id == log_id)
    )).scalar_one()


class TestConfirmWritesNote:
    @pytest.mark.asyncio
    async def test_editor_confirm_appends_text_and_stamps(self, db_session, world):
        """edit 级成员确认 → 追加到 text_content + 盖最近编辑 + 状态 confirmed。"""
        note = world["note"]
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note.id}:正文")
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log.id}/confirm")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirm_action"] == "confirmed"
        assert body["writeback"]["written"] is True
        text = await _note_text(db_session, note.id)
        assert "原有正文。" in text and "AI 起草的货币资金说明" in text
        assert "\n\n---\n\n" in text  # 分隔线
        # 盖了最近编辑
        from app.models.report_models import DisclosureNote
        n = (await db_session.execute(
            sa.select(DisclosureNote).where(DisclosureNote.id == note.id))).scalar_one()
        assert n.updated_by == world["editor"].id

    @pytest.mark.asyncio
    async def test_revise_writes_revised_text(self, db_session, world):
        """修订 → 写入的是 revised_content 而非 generated_content。"""
        note = world["note"]
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note.id}", content="原始AI草稿")
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log.id}/revise",
                                json={"revised_content": "审计师修订版正文"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["confirm_action"] == "revised"
        text = await _note_text(db_session, note.id)
        assert "审计师修订版正文" in text
        assert "原始AI草稿" not in text

    @pytest.mark.asyncio
    async def test_reviewer_without_edit_keeps_pending(self, db_session, world):
        """review 级（无 edit）确认 → 状态保持 pending + 返回原因 + 附注不变。"""
        note_id = world["note"].id
        before = await _note_text(db_session, note_id)
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note_id}")
        log_id = log.id
        async with _client(db_session, world["reviewer"]) as c:
            resp = await c.post(f"/api/ai-content/{log_id}/confirm")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirm_action"] == "pending"
        assert body["writeback"]["skipped"] is True
        assert "编辑权限" in body["writeback"]["reason"]
        assert await _status(db_session, log_id) == "pending"  # 真回滚
        assert await _note_text(db_session, note_id) == before  # 附注零改动

    @pytest.mark.asyncio
    async def test_outsider_confirm_is_403(self, db_session, world):
        """非本项目成员确认 → 403（缺陷 1：补了项目级鉴权）+ 附注零改动。"""
        note_id = world["note"].id
        before = await _note_text(db_session, note_id)
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note_id}")
        log_id = log.id
        async with _client(db_session, world["outsider"]) as c:
            resp = await c.post(f"/api/ai-content/{log_id}/confirm")
        assert resp.status_code == 403, resp.text
        assert await _status(db_session, log_id) == "pending"
        assert await _note_text(db_session, note_id) == before

    @pytest.mark.asyncio
    async def test_consol_lock_keeps_pending(self, db_session, world):
        """项目被合并锁定 → 保持 pending + 原因，附注不变。"""
        from app.models.core import Project

        note_id = world["note"].id
        before = await _note_text(db_session, note_id)
        await db_session.execute(
            sa.update(Project).where(Project.id == world["project"].id).values(consol_lock=True))
        await db_session.commit()
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note_id}")
        log_id = log.id
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log_id}/confirm")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirm_action"] == "pending"
        assert "合并锁定" in body["writeback"]["reason"]
        assert await _status(db_session, log_id) == "pending"
        assert await _note_text(db_session, note_id) == before

    @pytest.mark.asyncio
    async def test_confirm_publishes_note_section_saved(self, db_session, world, monkeypatch):
        """写回提交后发 NOTE_SECTION_SAVED，载荷与附注编辑端点同形（订阅方读 extra.section_code）。

        原写法 ``event_type="NOTE_SECTION_SAVED"`` 是枚举名不是取值、``source_id`` / ``detail`` 不是载荷字段，
        构造即抛 ValidationError 被 except 吞掉 ⇒ 下游（stale / 交付件 / 合并附注）从未收到通知。
        """
        from app.models.audit_platform_schemas import EventType
        from app.services import event_bus as event_bus_module

        published = []

        async def _capture(self, payload):
            published.append(payload)

        # 在类上替换：实例上 setattr 撤销时会把原方法写成实例属性，挡住之后的类级替换
        monkeypatch.setattr(type(event_bus_module.event_bus), "publish", _capture)

        note = world["note"]
        log = await _pending(db_session, world["project"].id, target_cell=f"note:{note.id}")
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log.id}/confirm")
        assert resp.status_code == 200, resp.text
        assert resp.json()["writeback"]["written"] is True
        assert len(published) == 1, published
        payload = published[0]
        assert payload.event_type == EventType.NOTE_SECTION_SAVED
        assert payload.project_id == world["project"].id
        assert payload.year == 2025
        assert payload.extra.get("section_code") == "八、1"

    @pytest.mark.asyncio
    async def test_note_in_other_project_is_not_written(self, db_session, world):
        """target_cell 指向别的项目的附注 ⇒ 不写（权限与合并锁只按日志所属项目判过）。"""
        from app.models.base import ProjectStatus
        from app.models.core import Project
        from app.models.report_models import DisclosureNote

        other = Project(name=f"他项目_{uuid.uuid4().hex[:6]}", client_name="客户乙",
                        status=ProjectStatus.execution, audit_year=2025)
        db_session.add(other)
        await db_session.flush()
        foreign = DisclosureNote(
            project_id=other.id, year=2025, note_section="八、1",
            section_title="货币资金", section_id=f"sec_{uuid.uuid4().hex[:8]}",
            text_content="他项目正文。", table_data={"rows": []},
        )
        db_session.add(foreign)
        await db_session.commit()

        log = await _pending(db_session, world["project"].id, target_cell=f"note:{foreign.id}")
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log.id}/confirm")
        assert resp.status_code == 200, resp.text
        assert resp.json()["writeback"]["written"] is False
        assert await _note_text(db_session, foreign.id) == "他项目正文。"

    @pytest.mark.asyncio
    async def test_workpaper_target_not_auto_written(self, db_session, world):
        """底稿类 target_cell 确认 → 状态 confirmed 但不自动写（缺陷 5）。"""
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"workpaper:{uuid.uuid4()}:E5")
        async with _client(db_session, world["editor"]) as c:
            resp = await c.post(f"/api/ai-content/{log.id}/confirm")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confirm_action"] == "confirmed"
        assert body["writeback"]["written"] is False
        assert "复制" in body["writeback"]["reason"]

    @pytest.mark.asyncio
    async def test_reject_requires_review_and_writes_nothing(self, db_session, world):
        """拒绝需 review 级；非成员 403；附注零改动。"""
        note = world["note"]
        before = await _note_text(db_session, note.id)
        log = await _pending(db_session, world["project"].id,
                             target_cell=f"note:{note.id}")
        async with _client(db_session, world["outsider"]) as c:
            denied = await c.post(f"/api/ai-content/{log.id}/reject")
        assert denied.status_code == 403
        async with _client(db_session, world["reviewer"]) as c:
            ok = await c.post(f"/api/ai-content/{log.id}/reject")
        assert ok.status_code == 200, ok.text
        assert ok.json()["confirm_action"] == "rejected"
        assert await _note_text(db_session, note.id) == before
