"""第 24 组：附注章节编辑盖「最近一次编辑」时间与编辑人（``updated_at`` / ``updated_by``）。

首版单章保存（PUT）从不赋值：``updated_at`` 只有 server_default、没有 onupdate ⇒ 时间停在最近一次批量写入，
批量写入的 ``expected_updated_at`` 复核看不见单章编辑。SQLite 内存库 + 真 ORM + 真路由；
编辑门禁 / 合并锁 / Redis / EventBus 打桩（鉴权另有 test_disclosure_notes_hardening）。
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import check_consol_lock, get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.routers import disclosure_notes
from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator
import tests.test_note_text_batch_endpoints as _batch
from tests.test_note_text_batch_endpoints import _Actor, _apply, _assert_error, _note, _previewed, _selection

batch_env = _batch.env  # fixture 需在本模块命名空间（pytest 按属性名注册）：批量写入端点的真库环境

YEAR = 2025
OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)
SECTION = "四、会计期间"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@pytest_asyncio.fixture
async def notes_env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, ProjectUser.__table__, DisclosureNote.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "p", "note")}
    async with factory() as s:
        s.add(Project(id=ids["p"], name="甲_2025", client_name="甲公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        s.add_all([
            ProjectUser(project_id=ids["p"], user_id=ids["me"], role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            DisclosureNote(id=ids["note"], project_id=ids["p"], year=YEAR, note_section=SECTION,
                           section_title="会计期间", text_content="<p>旧</p>", updated_at=OLD, updated_by=None),
        ])
        await s.commit()

    app = FastAPI()
    app.include_router(disclosure_notes.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _Actor(ids["me"])
    app.dependency_overrides[check_consol_lock] = lambda: None
    with patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)), \
            patch("app.deps._set_cached_permission", new=AsyncMock()), \
            patch("app.routers.disclosure_notes._assert_project_edit", new=AsyncMock()), \
            patch.object(DisclosureMutationCoordinator, "_redis", new=AsyncMock(return_value=None)), \
            patch("app.services.event_bus.event_bus.publish", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "ids": ids, "factory": factory}
    await engine.dispose()


async def _stamp(ctx: dict) -> tuple[datetime, uuid.UUID | None]:
    async with ctx["factory"]() as db:
        note = await db.get(DisclosureNote, ctx["ids"]["note"])
        return _utc(note.updated_at), note.updated_by


def _section_url(ctx: dict, tail: str = "") -> str:
    return f"/api/disclosure-notes/{ctx['ids']['p']}/{YEAR}/{tail}"


def _assert_stamped(stamp: tuple[datetime, uuid.UUID | None], ctx: dict, since: datetime) -> None:
    at, by = stamp
    assert at >= since and at - since < timedelta(minutes=1), (at, since)
    assert by == ctx["ids"]["me"]


class TestSingleChapterSave:
    @pytest.mark.asyncio
    async def test_save_stamps_time_and_editor(self, notes_env):
        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        resp = await notes_env["client"].put(f"/api/disclosure-notes/{notes_env['ids']['note']}",
                                             json={"text_content": "<p>新</p>"}, headers={"X-Mutation-Id": "m-1"})
        assert resp.status_code == 200, resp.text
        _assert_stamped(await _stamp(notes_env), notes_env, since)

    @pytest.mark.asyncio
    async def test_save_without_any_field_does_not_stamp(self, notes_env):
        resp = await notes_env["client"].put(f"/api/disclosure-notes/{notes_env['ids']['note']}",
                                             json={}, headers={"X-Mutation-Id": "m-2"})
        assert resp.status_code == 200, resp.text
        assert await _stamp(notes_env) == (OLD, None)


class TestSectionStateEdits:
    @pytest.mark.asyncio
    async def test_not_applicable_toggle_stamps_only_when_it_changes(self, notes_env):
        client, since = notes_env["client"], datetime.now(timezone.utc) - timedelta(seconds=1)
        resp = await client.patch(_section_url(notes_env, f"sections/{SECTION}"), json={"status": "draft"},
                                  headers={"X-Mutation-Id": "m-3"})
        assert resp.status_code == 200, resp.text
        assert await _stamp(notes_env) == (OLD, None), "状态没变不算编辑"
        resp = await client.patch(_section_url(notes_env, f"sections/{SECTION}"), json={"status": "not_applicable"},
                                  headers={"X-Mutation-Id": "m-4"})
        assert resp.status_code == 200, resp.text
        _assert_stamped(await _stamp(notes_env), notes_env, since)

    @pytest.mark.asyncio
    async def test_delete_and_restore_stamp(self, notes_env):
        client, since = notes_env["client"], datetime.now(timezone.utc) - timedelta(seconds=1)
        resp = await client.delete(_section_url(notes_env, f"sections/{SECTION}"), headers={"X-Mutation-Id": "m-5"})
        assert resp.status_code == 200, resp.text
        _assert_stamped(await _stamp(notes_env), notes_env, since)
        async with notes_env["factory"]() as db:  # 复位后单独看恢复
            note = await db.get(DisclosureNote, notes_env["ids"]["note"])
            note.updated_at, note.updated_by = OLD, None
            await db.commit()
        resp = await client.patch(_section_url(notes_env, f"restore/{notes_env['ids']['note']}"),
                                  headers={"X-Mutation-Id": "m-6"})
        assert resp.status_code == 200, resp.text
        _assert_stamped(await _stamp(notes_env), notes_env, since)


class TestFormulaEdits:
    """公式类端点改写发生在服务内部：改了单元格才盖章（服务打桩，只测路由的盖章）。"""

    @pytest.mark.parametrize(("endpoint", "target", "changed", "unchanged"), [
        ("clear-formulas", "app.services.note_wp_mapping_service.NoteWpMappingService.clear_formulas", 3, 0),
        ("restore-auto", "app.services.note_wp_mapping_service.NoteWpMappingService.restore_auto_mode", 2, 0),
        ("apply-formulas", "app.services.note_formula_generator.execute_note_formulas",
         {"executed": 2, "updated": 2}, {"executed": 2, "updated": 0}),
    ])
    @pytest.mark.asyncio
    async def test_stamps_only_when_cells_changed(self, notes_env, endpoint, target, changed, unchanged):
        client, url = notes_env["client"], _section_url(notes_env, f"{SECTION}/{endpoint}")
        with patch(target, new=AsyncMock(return_value=unchanged)):
            assert (await client.post(url)).status_code == 200
        assert await _stamp(notes_env) == (OLD, None)
        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        with patch(target, new=AsyncMock(return_value=changed)):
            assert (await client.post(url)).status_code == 200
        _assert_stamped(await _stamp(notes_env), notes_env, since)

    @pytest.mark.asyncio
    async def test_saving_user_formulas_stamps(self, notes_env):
        from app.services.note_formula_service import note_formula_service

        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        with patch.object(note_formula_service, "save_many", new=AsyncMock(return_value=[{"target": "B2"}])):
            resp = await notes_env["client"].put(_section_url(notes_env, f"{SECTION}/formulas"),
                                                 json={"formulas": [{"target": "B2", "formula": "=1"}]})
        assert resp.status_code == 200, resp.text
        _assert_stamped(await _stamp(notes_env), notes_env, since)


@pytest.mark.asyncio
async def test_batch_apply_sees_single_chapter_edit_made_after_preview(batch_env):
    """消费方：预览后有人单章改了编制指引（正文没动 ⇒ before_hash 不变），写入须 409 让用户重新预览。"""
    from app.services.disclosure_engine import DisclosureEngine

    source, preview, item = await _previewed(batch_env)
    async with batch_env["factory"]() as db:
        await DisclosureEngine(db).update_note(batch_env["ids"]["basic"], guidance_text="<p>他人改了编制指引</p>")
        await db.commit()
    resp = await _apply(batch_env, source, preview, [_selection(item)])
    assert _assert_error(resp, 409, "NOTE_BATCH_STALE_PREVIEW")["stale_notes"] == ["一、1"]
    assert (await _note(batch_env, "basic")).text_content == "<p>旧基本情况</p>"


# ── 守卫：附注路由的每个写端点都已归类（盖章 / 不盖章且写明理由）────────────────────

_ROUTER = Path(disclosure_notes.__file__)
_STAMP_CALLS = {"stamp_note_edit", "stamp_section_edit"}
#: 不盖章的写端点：不改章节内容，或不是人工编辑（盖了会让「附注侧有手动编辑」冲突判定误报）
_NOT_EDITS = {
    "generate_notes": "按模板重新生成 / 刷新（正文受 is_local_override 保护、表格三态合并），不是人工编辑",
    "set_formula_gray": "只改项目向导状态，不写章节",
    "pull_from_workpapers": "只刷新表格的同步簿记键（_source / _last_sync_at）",
    "validate_notes": "写校验结果表，不写章节",
    "confirm_finding": "写校验结果表，不写章节",
    "export_word": "导出，不写章节",
    "upload_history": "上传历史附注文件，不写本年章节",
    "ai_fill_note_section": "只返回预览并登记对话消息，采纳落库走 PUT",
    "batch_ai_fill_notes": "只返回预览，不落库",
}


def _write_routes() -> dict[str, ast.AsyncFunctionDef]:
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    routes = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {"post", "put", "patch", "delete"}
                for d in node.decorator_list):
            routes[node.name] = node
    return routes


def _stamps(func: ast.AsyncFunctionDef) -> bool:
    """AST 判据（注释 / docstring 不算）：调了盖章函数，或调 ``update_note`` 时传了 ``user_id``。"""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name in _STAMP_CALLS or (name == "update_note" and any(k.arg == "user_id" for k in node.keywords)):
                return True
    return False


def test_every_write_route_is_classified():
    routes = _write_routes()
    assert len(routes) >= 15, "解析不到写端点，判据空转"
    unclassified = sorted(n for n, f in routes.items() if n not in _NOT_EDITS and not _stamps(f))
    assert not unclassified, f"写端点既不盖「最近一次编辑」也没登记不盖的理由：{unclassified}"
    stale = sorted(n for n in _NOT_EDITS if n not in routes or _stamps(routes[n]))
    assert not stale, f"豁免清单失效（端点已不存在或已盖章）：{stale}"
