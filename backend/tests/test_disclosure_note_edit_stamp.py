"""第 24 组：附注章节编辑盖「最近一次编辑」时间与编辑人（``updated_at`` / ``updated_by``）。

首版单章保存（PUT）从不赋值：``updated_at`` 只有 server_default、没有 onupdate ⇒ 时间停在最近一次批量写入，
批量写入的 ``expected_updated_at`` 复核看不见单章编辑。SQLite 内存库 + 真 ORM + 真路由；
编辑门禁 / 合并锁 / Redis / EventBus 打桩（鉴权另有 test_disclosure_notes_hardening）。
"""

from __future__ import annotations

import ast
import re
import textwrap
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
        # formula-global-settings-sync：保存端点经 note_settings.save_section（差量写本项目适配 + 物化）
        from app.services.formula_settings import note_settings

        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        saved = {"formulas": [{"target": "B2"}], "loaded": {}, "events": []}
        with patch.object(note_settings, "save_section", new=AsyncMock(return_value=saved)):
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


# ── 守卫（二）：其他模块改附注（spec disclosure-note-template-word-realignment Task 19，design §5）──────────
# 行为测试见 test_note_edit_stamp_writers.py / test_note_prior_year_import_stamp.py / test_note_group_template_stamp_pg.py。

_APP = _ROUTER.parents[1]  # backend/app

#: 以用户身份改附注的写入方：函数体里必须写编辑人（调盖章函数 / ``x.updated_by = …`` / 裸 SQL 写 updated_by 列）
_USER_WRITERS: dict[str, tuple[str, ...]] = {
    "services/note_prior_year_import_service.py": (
        "NotePriorYearImportService.import_from_docx", "NotePriorYearImportService.inherit_from_prior_year"),
    "services/group_note_baseline_service.py": ("GroupNoteBaselineService.apply_baseline",),
    "services/note_group_template_service.py": ("NoteGroupTemplateService._upsert_section",),
    "services/triple_format_adapter.py": ("DisclosureNoteAdapter.update_note_from_structure",),
    "services/note_offline_import_service.py": ("NoteOfflineImportService._persist_guidance_from_meta",),
    "services/note_wp_mapping_service.py": ("NoteWpMappingService.toggle_cell_mode",),
    "routers/recycle_bin.py": ("restore_item",),
    "services/procedure_trim_note_linkage.py": ("apply_note_linkage",),
    "services/note_text_batch_apply.py": ("apply_batch",),
    "services/wp_disclosure_sync_service.py": ("sync_from_workpaper", "WpDisclosureSyncService.sync_from_html"),
    "services/disclosure_engine.py": ("DisclosureEngine.update_note",),
}
#: 调用上面这些写入方必须把操作人传进去：关键字缺省为 None，漏传只记时间不记人（静默退化）
_ACTOR_KEYWORDS: dict[str, str] = {
    "import_from_docx": "user_id", "inherit_from_prior_year": "user_id", "apply_baseline": "user_id",
    "distribute_template": "user_id", "_apply_template_to_project": "user_id", "_upsert_section": "user_id",
    "update_note_from_structure": "user_id", "_persist_guidance_from_meta": "user_id",
    "toggle_cell_mode": "user_id", "apply_note_linkage": "actor_user_id",
}
#: 系统路径：写附注但不是人工编辑 —— 不许写编辑人；唯一允许的是「有操作人才记」：``if X is not None: y.updated_by = X``
_SYSTEM_WRITERS: dict[str, tuple[str, ...]] = {
    "services/formula_push/engine.py": ("_push_note",),
    "services/formula_runtime/adapters/note.py": ("NoteMutationAdapter.apply_many", "NoteMutationAdapter.restore_many"),
    "services/note_template_reflow_service.py": ("apply_reflow_section",),
    "services/disclosure_engine.py": (
        "DisclosureEngine.generate_notes", "DisclosureEngine.update_note_values", "DisclosureEngine.get_note_detail"),
    "services/note_cross_reference_service.py": ("NoteCrossReferenceService.update_all_references",),
    "services/note_conversion_service.py": (
        "NoteConversionService._map_disclosure_notes", "NoteConversionService._restore_note_from_snapshot"),
    "services/report_note_sync_service.py": ("ReportNoteSyncService._sync_real",),
    "services/note_formula_generator.py": ("execute_note_formulas",),
    "services/note_formula_service.py": ("NoteFormulaService.save_many",),
    "services/formula_settings/note_settings.py": ("materialize", "save_section", "_import_legacy"),
    "services/note_wp_mapping_service.py": ("NoteWpMappingService.clear_formulas", "NoteWpMappingService.restore_auto_mode"),
    "services/note_trim_service.py": ("NoteTrimService.auto_trim_v2",),
    "services/consol_disclosure_service.py": ("ConsolDisclosureService.save_consol_notes",),
    "routers/note_wp_mapping.py": ("refresh_all_bindings",),
    "routers/disclosure_notes.py": ("pull_from_workpapers",),
}
_SQL_SET = re.compile(r"\bSET\b", re.IGNORECASE)


def _function(rel: str, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    scope: list[ast.stmt] = ast.parse((_APP / rel).read_text(encoding="utf-8-sig")).body
    *classes, name = qualname.split(".")
    for cls in classes:
        found = [n for n in scope if isinstance(n, ast.ClassDef) and n.name == cls]
        assert found, f"{rel} 里没有类 {cls}（改名了？判据空转）"
        scope = found[0].body
    found = [n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert found, f"{rel} 里没有 {qualname}（改名了？判据空转）"
    return found[0]


def _body_nodes(func: ast.AST):
    """函数体全部节点，去掉 docstring（说明文字里写 updated_by 不算写了）。注释本就不进 AST。"""
    body = list(func.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    for stmt in body:
        yield from ast.walk(stmt)


def _editor_writes(func: ast.AST) -> list[ast.AST]:
    """写编辑人的节点：盖章调用 / ``x.updated_by = …`` / ``d["updated_by"] = …`` / ``updated_by=…`` 关键字 /
    字典键 ``"updated_by"`` / 裸 SQL ``SET … updated_by``。"""
    out: list[ast.AST] = []
    for node in _body_nodes(func):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name in _STAMP_CALLS:
                out.append(node)
            out.extend(k for k in node.keywords if k.arg == "updated_by")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "updated_by" or isinstance(t, ast.Subscript) \
                        and isinstance(t.slice, ast.Constant) and t.slice.value == "updated_by":
                    out.append(t)
        elif isinstance(node, ast.Dict):
            out.extend(k for k in node.keys if isinstance(k, ast.Constant) and k.value == "updated_by")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "updated_by" in node.value \
                and _SQL_SET.search(node.value):
            out.append(node)
    return out


def _is_none_guard(node: ast.AST, value: ast.AST) -> bool:
    """``if <value> is not None:``"""
    test = getattr(node, "test", None)
    return isinstance(node, ast.If) and isinstance(test, ast.Compare) and len(test.ops) == 1 \
        and isinstance(test.ops[0], ast.IsNot) and isinstance(test.comparators[0], ast.Constant) \
        and test.comparators[0].value is None and ast.dump(test.left) == ast.dump(value)


def _unguarded_editor_writes(func: ast.AST) -> list[str]:
    """系统路径里不被「有操作人才记」守住的编辑人写入（守护只认 if 的真分支）。"""
    parents = {child: parent for parent in ast.walk(func) for child in ast.iter_child_nodes(parent)}
    bad = []
    for node in _editor_writes(func):
        assign = parents.get(node)
        if isinstance(node, ast.Attribute) and isinstance(assign, ast.Assign):
            prev, cur = assign, parents.get(assign)
            while cur is not None and not (_is_none_guard(cur, assign.value) and prev in cur.body):
                prev, cur = cur, parents.get(cur)
            if cur is not None:
                continue
        bad.append(f"L{getattr(node, 'lineno', '?')}: {ast.unparse(node)[:80]}")
    return bad


@pytest.mark.parametrize(("rel", "qualname"), [(r, q) for r, qs in _USER_WRITERS.items() for q in qs])
def test_user_writer_writes_editor(rel, qualname):
    assert _editor_writes(_function(rel, qualname)), (
        f"{rel}::{qualname} 以用户身份改附注却不写「最近一次编辑」（盖章函数 / updated_by）")


@pytest.mark.parametrize(("rel", "qualname"), [(r, q) for r, qs in _SYSTEM_WRITERS.items() for q in qs])
def test_system_writer_never_overwrites_editor(rel, qualname):
    bad = _unguarded_editor_writes(_function(rel, qualname))
    assert not bad, f"{rel}::{qualname} 是系统路径，却写了编辑人（会清空或冒认上一位编辑人）：{bad}"


def test_callers_pass_the_actor():
    calls: dict[str, list[str]] = {name: [] for name in _ACTOR_KEYWORDS}
    missing: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):  # 个别文件带 BOM
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name in calls:
                where = f"{path.relative_to(_APP).as_posix()}:L{node.lineno}"
                calls[name].append(where)
                if not any(k.arg == _ACTOR_KEYWORDS[name] for k in node.keywords):
                    missing.append(f"{where} {name}(…) 没传 {_ACTOR_KEYWORDS[name]}")
    assert all(calls.values()), f"找不到调用点（改名了？判据空转）：{[n for n, v in calls.items() if not v]}"
    assert not missing, missing


def test_no_note_code_assigns_null_editor():
    """附注相关代码里不许出现 ``x.updated_by = None`` / ``updated_by=None``（清空上一位编辑人）。"""
    offenders = []
    for path in sorted(_APP.rglob("*.py")):
        src = path.read_text(encoding="utf-8-sig")
        if "DisclosureNote" not in src and "disclosure_notes" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and node.value.value is None \
                    and any(isinstance(t, ast.Attribute) and t.attr == "updated_by" for t in node.targets) \
                    or isinstance(node, ast.keyword) and node.arg == "updated_by" \
                    and isinstance(node.value, ast.Constant) and node.value.value is None:
                offenders.append(f"{path.relative_to(_APP).as_posix()}:L{getattr(node, 'lineno', '?')}")
    assert not offenders, offenders


def test_guard_helpers_self_check():
    """判据自检：守护只认 if 真分支、docstring 不算、SQL 文本算、字典键算。"""
    def fn(src: str) -> ast.AST:
        return ast.parse(textwrap.dedent(src)).body[0]

    assert _unguarded_editor_writes(fn("def f(n, ctx):\n    n.updated_by = ctx.triggered_by\n"))
    assert not _unguarded_editor_writes(fn(
        "def f(n, ctx):\n    if ctx.triggered_by is not None:\n        n.updated_by = ctx.triggered_by\n"))
    assert _unguarded_editor_writes(fn(
        "def f(n, ctx):\n    if ctx.triggered_by is not None:\n        pass\n    else:\n        n.updated_by = ctx.triggered_by\n"))
    assert _unguarded_editor_writes(fn(
        "def f(n, ctx, u):\n    if u is not None:\n        n.updated_by = ctx.triggered_by\n")), "守护的变量与赋值不一致也不算"
    assert _unguarded_editor_writes(fn('def f(db):\n    db.execute("UPDATE t SET a = 1, updated_by = :u")\n'))
    assert _unguarded_editor_writes(fn('def f(db, u):\n    db.execute(q.values({"updated_by": u}))\n'))
    assert not _editor_writes(fn('def f(db):\n    """UPDATE t SET updated_by = :u（只是说明）"""\n    return 1\n'))
    assert _editor_writes(fn("def f(n, u):\n    stamp_note_edit(n, u)\n"))
