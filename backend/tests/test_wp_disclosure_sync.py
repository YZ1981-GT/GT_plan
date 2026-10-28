"""Tests for POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper.

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1 推荐选项 A

Strategy: bypass real DB by mocking `sync_from_workpaper` service + `get_db` dep,
so we focus on router-level behavior (status codes, RBAC, schema validation).
A separate service-level integration test covers the create/update branches.

RBAC（项目成员判定）三条用例走权限世界（``tests/authz_world.py``，SQLite 内存库）：身份是真实用户与目标项目上
的成员行（取 ``assignment_service.ROLE_MAP`` 对委派角色给出的值，未登记角色取 ``UNMAPPED_ROLE``），由生产的
``require_project_access("edit")`` / ``assert_project_permission`` 判定，不替换门禁
（partner-manager-edit-permission 需求 12.1）；同步本身与同步后的自动校验打桩计数。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.routers.wp_disclosure_sync as wp_disclosure_sync_module
import app.services.note_readiness_service as note_readiness_service
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_disclosure_sync import router as wp_disclosure_sync_router
from app.services.assignment_service import ROLE_MAP, map_assignment_role
from tests.authz_world import TARGET_PROJECT_ID, sqlite_world

# ─── Fixtures ────────────────────────────────────────────────────────────────


ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUDITOR_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_app(*, role: UserRole = UserRole.admin) -> tuple[FastAPI, MagicMock]:
    """Build a FastAPI app with mocked deps. Returns (app, mock_db)."""
    app = FastAPI()
    app.include_router(wp_disclosure_sync_router)

    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.add = MagicMock()

    async def _override_db():
        yield mock_db

    user_id = ADMIN_USER_ID if role == UserRole.admin else AUDITOR_USER_ID

    async def _override_user():
        return User(
            id=user_id,
            username="user",
            email="user@test.com",
            hashed_password="x",
            role=role,
            is_active=True,
            is_deleted=False,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app, mock_db


# ─── Service-layer unit tests (pure function, no FastAPI) ────────────────────


class TestServiceHelpers:
    """Direct tests for service-level helper functions."""

    def test_count_rows_synced_empty(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced(None) == 0
        assert _count_rows_synced({}) == 0

    def test_count_rows_synced_with_data(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced({"a": [1, 2, 3]}) == 3
        assert _count_rows_synced({"a": [1, 2], "b": [{"x": 1}]}) == 3

    def test_count_rows_synced_skips_non_lists(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced({"a": "not_a_list", "b": [1]}) == 1

    def test_count_rows_synced_skips_metadata_keys(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced({
            "主表": [{"a": 1}, {"a": 2}],
            "_note_texts": [{"section": "x", "text": "hello"}],
        }) == 2

    def test_extract_and_format_note_texts(self):
        from app.services.wp_disclosure_sync_service import (
            _extract_note_texts,
            _format_note_texts,
        )
        clean, texts = _extract_note_texts({
            "主表": [{"a": 1}],
            "_note_texts": [
                {"section": "s1", "title": "说明", "text": "正文A"},
                {"section": "s2", "text": "  "},
            ],
        })
        assert clean == {"主表": [{"a": 1}]}
        assert len(texts) == 2
        assert "【说明】\n正文A" in _format_note_texts(texts)

    def test_derive_section_title_with_space(self):
        from app.services.wp_disclosure_sync_service import _derive_section_title
        assert _derive_section_title("五-1-1 应收账款") == "应收账款"
        assert _derive_section_title("六-2 存货") == "存货"

    def test_derive_section_title_no_space(self):
        from app.services.wp_disclosure_sync_service import _derive_section_title
        assert _derive_section_title("五-1-1") == "五-1-1"
        assert _derive_section_title("") == ""

    # ── 旧表名清理（spec d2-ar-disclosure-template-alignment，Requirement 8）──

    def test_extract_removed_table_keys(self):
        from app.services.wp_disclosure_sync_service import _extract_removed_table_keys

        clean, keys = _extract_removed_table_keys({
            "主表": [{"a": 1}],
            "_removed_table_keys": ["旧表A", " 旧表B ", "旧表A", "", "_note_texts"],
        })
        assert clean == {"主表": [{"a": 1}]}
        # 去重 + strip + 丢弃空值与元数据键（元数据不可经此删除）
        assert keys == ["旧表A", "旧表B"]

    def test_extract_removed_table_keys_absent_or_invalid(self):
        from app.services.wp_disclosure_sync_service import _extract_removed_table_keys

        assert _extract_removed_table_keys({"主表": []}) == ({"主表": []}, [])
        assert _extract_removed_table_keys(None) == ({}, [])
        # 非列表值 → 忽略（幂等，不抛错）
        assert _extract_removed_table_keys({"_removed_table_keys": "旧表A"}) == ({}, [])

    def test_drop_removed_tables_skips_pushed_keys(self):
        """Property 7：删除旧键但绝不删本次推送的表名。"""
        from app.services.wp_disclosure_sync_service import _drop_removed_tables

        sub = {"旧表A": [{"x": 1}], "新表": [{"y": 2}], "保留表": []}
        cols = {"旧表A": [{"key": "x"}], "新表": [{"key": "y"}]}
        dropped = _drop_removed_tables(sub, cols, ["旧表A", "新表"], pushed_keys={"新表"})

        assert dropped == ["旧表A"]
        assert sub == {"新表": [{"y": 2}], "保留表": []}
        assert cols == {"新表": [{"key": "y"}]}

    def test_drop_removed_tables_unknown_key_is_noop(self):
        from app.services.wp_disclosure_sync_service import _drop_removed_tables

        sub = {"主表": [{"a": 1}]}
        cols = {"主表": [{"key": "a"}]}
        assert _drop_removed_tables(sub, cols, ["不存在的表"], pushed_keys=set()) == []
        assert sub == {"主表": [{"a": 1}]}
        assert cols == {"主表": [{"key": "a"}]}


# ─── Router-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_happy_path_admin(monkeypatch):
    """admin user + valid payload → 200 + service called with correct args."""
    app, _mock_db = _make_app(role=UserRole.admin)

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "应收账款附注C",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {
            "subtable_aging": [{"v": 1}, {"v": 2}],
            "subtable_top5": [{"v": 3}],
        },
        "current_standard": "soe_standalone",
        "year": 2025,
    }

    fake_now = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": fake_now.isoformat(),
        "rows_synced": 3,
        "created": True,
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["section_id"] == "五-1-1 应收账款"
    assert body["rows_synced"] == 3
    assert body["created"] is True
    assert body["synced_at"] == fake_now.isoformat()

    # Verify service called with kwargs
    assert mock_svc.await_count == 1
    kwargs = mock_svc.await_args.kwargs
    assert kwargs["wp_id"] == WP_ID
    assert kwargs["section_id"] == "五-1-1 应收账款"
    assert kwargs["sheet_name"] == "应收账款附注C"
    assert kwargs["current_standard"] == "soe_standalone"
    assert kwargs["year"] == 2025
    assert kwargs["user"].id == ADMIN_USER_ID


@pytest.mark.asyncio
async def test_sync_response_keeps_service_feedback_fields():
    """服务层返回的反馈字段原样到达前端（spec note-pull-followup-closure R3）。

    原响应模型只声明了 6 个字段，FastAPI 按 response_model 过滤 ⇒ ``row_scope_unresolved``（行级合并 fail closed）
    与 ``row_scope_unresolved_reasons`` 前端读到的恒为 undefined，提示从未出现过；``push_kept`` 同理。
    """
    app, _mock_db = _make_app(role=UserRole.admin)
    kept = [{"table": "货币资金", "row": "库存现金", "period": "end", "field": "end_amount", "kind": "cell",
             "pushed": 390.0, "incoming": 999}]
    fake_result = {
        "success": True, "section_id": "五、1", "synced_at": "2026-10-27T00:00:00+00:00", "rows_synced": 4,
        "created": False, "revived": False, "blocked_by_manual_override": False, "texts_synced": 0,
        "row_scoped_tables": [], "row_scope_unresolved": ["外币货币性项目"],
        "row_scope_unresolved_reasons": {"外币货币性项目": "项目准则未设置"}, "push_kept": kept,
    }
    payload = {"wp_id": str(WP_ID), "sheet_name": "附注披露信息(上市公司)", "section_id": "五、1",
               "sub_table_data": {"货币资金": [{"label": "库存现金", "end_amount": 999}]},
               "current_standard": "listed_standalone", "year": 2025}
    with patch("app.routers.wp_disclosure_sync.sync_from_workpaper", new=AsyncMock(return_value=fake_result)), \
         patch("app.deps.set_rls_context", new=AsyncMock()), \
         patch.object(wp_disclosure_sync_module, "_autorun_validation", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_scope_unresolved"] == ["外币货币性项目"]
    assert body["row_scope_unresolved_reasons"] == {"外币货币性项目": "项目准则未设置"}
    assert body["push_kept"] == kept
    # 服务层返回的每个键都在响应里（新加字段忘了声明会再次被过滤）
    assert set(fake_result) <= set(body), set(fake_result) - set(body)


def _returned_keys(func_name: str) -> set[str]:
    """服务函数里所有 ``return {...}`` 字面量与 ``return _helper(...)``（同文件、返回字面量的辅助函数）的键。"""
    import ast
    import inspect

    import app.services.wp_disclosure_sync_service as svc

    tree = ast.parse(inspect.getsource(svc))
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def dict_keys(fn) -> set[str]:
        keys: set[str] = set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Dict):
                keys |= {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
            elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) \
                    and node.value.func.id in funcs:
                keys |= dict_keys(funcs[node.value.func.id])
        return keys

    return dict_keys(funcs[func_name])


@pytest.mark.parametrize(("func_name", "model", "handled"), [
    ("sync_from_workpaper", wp_disclosure_sync_module.SyncFromWorkpaperResponse, {"synced", "skipped_reason"}),
    ("sync_from_html", wp_disclosure_sync_module.SyncFromHtmlResponse, set()),
])
def test_response_models_declare_every_service_key(func_name, model, handled):
    """服务返回的每个键都在响应模型里（否则 FastAPI 按 response_model 过滤掉、前端读到 undefined）。

    ``handled``：路由单独处理的形态（没有审计年度 ⇒ 422，见 test_sync_without_audit_year_is_422）。"""
    keys = _returned_keys(func_name)
    assert {"success", "push_kept", "row_scope_unresolved"} <= keys, "判据空转：没扫到服务的返回字典"
    missing = keys - set(model.model_fields) - handled
    assert not missing, f"{func_name} 返回了响应模型没声明的键（会被过滤）：{sorted(missing)}"


@pytest.mark.asyncio
async def test_sync_without_audit_year_is_422():
    """项目没有审计年度、载荷也没带年度：服务层不写入并回 skipped_reason ⇒ 422 中文原因（原来构造响应模型缺字段 ⇒ 500）。"""
    app, _mock_db = _make_app(role=UserRole.admin)
    payload = {"wp_id": str(WP_ID), "sheet_name": "附注", "section_id": "五、1",
               "sub_table_data": {"货币资金": []}, "current_standard": "listed_standalone"}
    with patch("app.routers.wp_disclosure_sync.sync_from_workpaper",
               new=AsyncMock(return_value={"synced": 0, "skipped_reason": "未设置审计年度"})), \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper", json=payload)
    assert resp.status_code == 422, resp.text
    assert "未设置审计年度" in resp.text


@pytest.mark.asyncio
async def test_batch_sync_without_audit_year_is_422_and_rolls_back():
    """批量端点同口径（L3 国企、G7 走批量）：子章节回 skipped_reason ⇒ 整批回滚、422 中文原因。

    原来把跳过结果当成功汇总：读 ``results[-1]["synced_at"]`` KeyError ⇒ 500「附注批量同步失败: 'synced_at'」。
    服务层用真实 ``sync_batch_from_workpaper``，只替换它调用的单章节同步。"""
    app, mock_db = _make_app(role=UserRole.admin)
    payload = {"wp_id": str(WP_ID), "current_standard": "soe_standalone", "items": [
        {"section_id": "八、49", "sheet_name": "附注", "sub_table_data": {"长期借款": []}},
        {"section_id": "八、45", "sheet_name": "附注", "sub_table_data": {"一年内到期的非流动负债": []}},
    ]}
    single = AsyncMock(return_value={"synced": 0, "skipped_reason": "未设置审计年度"})
    with patch("app.services.wp_disclosure_sync_service.sync_from_workpaper", new=single), \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-batch-from-workpaper", json=payload)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "附注未同步：未设置审计年度"
    assert single.await_count == 1, "第一节就没写成，后面的章节不再同步"
    mock_db.commit.assert_not_awaited()
    mock_db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_sync_422_when_section_id_missing():
    """Pydantic catches missing required field → 422."""
    app, _mock_db = _make_app()

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        # missing section_id
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_section_id_empty():
    """min_length=1 rejects empty string → 422."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_section_id_blank_passed_to_service():
    """Whitespace-only section_id passes Pydantic min_length but service rejects → 422."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "   ",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    async def _raise(*args, **kwargs):
        raise ValueError("section_id 不能为空")

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(side_effect=_raise),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_wp_id_invalid():
    """Invalid wp_id (not a UUID) → 422 from Pydantic."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": "not-a-uuid",
        "sheet_name": "C-sheet",
        "section_id": "五-1-1",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )
    assert resp.status_code == 422


# ─── RBAC：权限世界里的真实成员行，生产门禁判定 ────────────────────────────────

_GATE = "app.deps.assert_project_permission"
_TARGET_SYNC_PATH = f"/api/projects/{TARGET_PROJECT_ID}/disclosure-notes/sync-from-workpaper"
_RBAC_PAYLOAD = {
    "wp_id": str(WP_ID),
    "sheet_name": "C-sheet",
    "section_id": "五-1-1 应收账款",
    "sub_table_data": {},
    "current_standard": "soe_standalone",
}


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_world(monkeypatch) as w:
        yield w


async def _post_as_member(world, user, payload, *, result=None):
    """以世界里的 ``user`` 向目标项目发同步请求；同步与同步后的自动校验打桩计数。"""
    sync = world.stub(wp_disclosure_sync_module, "sync_from_workpaper", returns=result)
    validation = world.stub(note_readiness_service, "run_validation_best_effort", returns=None)
    async with world.client(wp_disclosure_sync_router, user=user) as client:
        resp = await client.post(_TARGET_SYNC_PATH, json=payload)
    return resp, sync, validation, client


@pytest.mark.asyncio
async def test_sync_403_for_non_admin_without_project_access(world):
    """auditor without project_users record on the target project → 403（在另一项目上是 edit 级也不行）。"""
    identity = await world.non_member()

    resp, sync, validation, client = await _post_as_member(world, identity.user, _RBAC_PAYLOAD)

    assert (resp.status_code, resp.json()) == (403, {"detail": "权限不足"})
    assert (sync.count, validation.count) == (0, 0)
    client.assert_passed(_GATE, times=1)


@pytest.mark.asyncio
async def test_sync_403_for_readonly_user(world):
    """Non-admin member whose project_users row is readonly → 403.

    成员行取 ROLE_MAP 对未登记委派角色的兜底（UNMAPPED_ROLE = readonly, readonly），
    require_project_access('edit') 应拒绝。
    """
    role, level = map_assignment_role("观察员")
    identity = await world.member(level, role)
    assert (identity.member.role.value, identity.member.permission_level.value) == ("readonly", "readonly")

    resp, sync, validation, client = await _post_as_member(world, identity.user, _RBAC_PAYLOAD)

    assert (resp.status_code, resp.json()) == (403, {"detail": "权限不足"})
    assert (sync.count, validation.count) == (0, 0)
    client.assert_passed(_GATE, times=1)


@pytest.mark.asyncio
async def test_sync_with_edit_user_succeeds(world):
    """Non-admin member whose project_users row is edit（委派角色 auditor → ROLE_MAP 值 (auditor, edit)）→ 200."""
    role, level = ROLE_MAP["auditor"]
    identity = await world.member(level, role)

    payload = {**_RBAC_PAYLOAD, "sub_table_data": {"st1": [{"v": 1}]}, "year": 2025}
    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": "2026-05-26T10:00:00+00:00",
        "rows_synced": 1,
        "created": True,
    }

    resp, sync, validation, client = await _post_as_member(world, identity.user, payload, result=fake_result)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] is True
    # 服务没返回的反馈字段取默认值（2026-10-27 起响应模型声明了服务层的全部键，spec note-pull-followup-closure R3）
    assert body == {**fake_result, "texts_synced": 0, "revived": False, "blocked_by_manual_override": False,
                    "row_scoped_tables": [], "row_scope_unresolved": [], "row_scope_unresolved_reasons": {},
                    "push_kept": [], "skipped": False, "reason": None}
    ((args, kwargs),) = sync.calls
    assert args[1] == TARGET_PROJECT_ID
    assert (kwargs["wp_id"], kwargs["section_id"], kwargs["user"].id) == (WP_ID, "五-1-1 应收账款", identity.user.id)
    assert validation.count == 1  # 同步成功后自动补跑一次附注校验
    client.assert_passed(_GATE, times=1)


@pytest.mark.asyncio
async def test_sync_500_on_unexpected_error():
    """Unexpected service exception → 500 with message."""
    app, _mock_db = _make_app(role=UserRole.admin)

    async def _raise_generic(*args, **kwargs):
        raise RuntimeError("DB connection lost")

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(side_effect=_raise_generic),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 500
    assert "DB connection lost" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_sync_year_optional():
    """payload omitting year is accepted (service applies default)."""
    app, _mock_db = _make_app()

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
        # year intentionally omitted
    }

    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": "2026-05-26T10:00:00+00:00",
        "rows_synced": 0,
        "created": True,
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200
    # year passed through as None
    assert mock_svc.await_args.kwargs["year"] is None

@pytest.mark.asyncio
async def test_sync_batch_happy_path():
    """Batch sync endpoint calls service once and returns summary."""
    app, _mock_db = _make_app(role=UserRole.admin)

    payload = {
        "wp_id": str(WP_ID),
        "current_standard": "soe",
        "items": [
            {
                "sheet_name": "附注披露信息（国企）",
                "section_id": "七、本期纳入合并报表范围的子公司基本情况",
                "sub_table_data": {"主表": [{"a": 1}]},
            },
            {
                "sheet_name": "附注披露信息（国企）",
                "section_id": "八、18",
                "sub_table_data": {
                    "长期股权投资分类": [{"a": 1}, {"a": 2}],
                    "_note_texts": [{"section": "x", "title": "说明", "text": "正文"}],
                },
            },
        ],
    }

    fake_result = {
        "success": True,
        "sections_synced": 2,
        "rows_synced": 3,
        "texts_synced": 1,
        "synced_at": "2026-07-19T10:00:00+00:00",
        "results": [],
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_batch_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-batch-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sections_synced"] == 2
    assert body["rows_synced"] == 3
    assert body["texts_synced"] == 1
    assert mock_svc.await_count == 1
    assert len(mock_svc.await_args.kwargs["items"]) == 2

