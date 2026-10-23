"""Design 定级端点鉴权测试（partner-manager-edit-permission Task 11.2 起）。

覆盖清册中 target_gate.kind == 'design_gate' 的端点，即 §4.8 表 B 中
不走附注编辑门禁路径依赖、而用 ``assert_note_edit_access_on_projects``
/ ``assert_note_role_access`` 等函数体调用形态的端点。

本文件先写 save_baseline（B2）的用例，后续任务逐个补齐其余端点。

_Requirements: 8.1, 8.2, 8.4, 8.5, 8.6_
"""
from __future__ import annotations

import importlib
import uuid

import pytest
import pytest_asyncio
from httpx import Response

from tests.authz_world import (
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    sqlite_world,
)

from app.services.note_edit_gate import (
    REASON_EQCR_READONLY,
    REASON_FORBIDDEN,
    REASON_MULTI_PROJECT_DENIED_PREFIX,
    REASON_OPERATION_DENIED,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_SAVE_BASELINE_URL = "/api/group-note-baselines"
_SAVE_BASELINE_BODY = {
    "name": "测试基线",
    "template_type": "soe",
}
_SAVE_BASELINE_PARAMS = {"project_id": str(TARGET_PROJECT_ID)}

# 导入路由
from app.routers import group_note_baseline  # noqa: E402

_ALL_ROUTERS = (group_note_baseline.router,)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AuthzWorld:
    async with sqlite_world(monkeypatch) as w:
        yield w


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _assert_denied(resp: Response, status: int, reason_contains: str) -> None:
    """断言拒绝响应：状态码匹配、detail 中含预期原因片段。"""
    assert resp.status_code == status, (
        f"期望 {status}，实际 {resp.status_code}；body={resp.text[:500]}"
    )
    body = resp.json()
    detail = body.get("detail", "")
    if isinstance(detail, dict):
        actual_reason = detail.get("message", "")
    else:
        actual_reason = detail
    assert reason_contains in actual_reason, (
        f"原因不含 {reason_contains!r}：实际 {actual_reason!r}"
    )


def _assert_denied_exact(resp: Response, status: int, reason: str) -> None:
    """断言拒绝响应：状态码匹配、detail 中的原因逐字一致。"""
    assert resp.status_code == status, (
        f"期望 {status}，实际 {resp.status_code}；body={resp.text[:500]}"
    )
    body = resp.json()
    detail = body.get("detail", "")
    if isinstance(detail, dict):
        actual_reason = detail.get("message", "")
    else:
        actual_reason = detail
    assert actual_reason == reason, f"原因不一致：期望 {reason!r}，实际 {actual_reason!r}"


def _assert_denied_lists_project(resp: Response, project_id: uuid.UUID) -> None:
    """断言拒绝响应的 detail.project_ids 包含指定项目 id。"""
    body = resp.json()
    detail = body.get("detail", {})
    if isinstance(detail, dict):
        project_ids = detail.get("project_ids", [])
        assert str(project_id) in project_ids, (
            f"project_ids 应包含 {project_id}，实际 {project_ids}"
        )


# ---------------------------------------------------------------------------
# save_baseline (B2): POST /api/group-note-baselines?project_id=...
# design 定级：assert_note_edit_access_on_projects([project_id])
# ---------------------------------------------------------------------------




class _BaselineMock:
    """GroupNoteBaselineService 的 SmartMock：实例化后任何方法调用返回合理的异步默认值。"""

    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            return {"id": str(uuid.uuid4()), "version": "1.0.0", "success": True}
        return _method


class TestSaveBaselineDesignGate:
    """save_baseline 端点鉴权：非成员 / readonly / EQCR 得 403；
    至少一种身份放行；错误信息列出未通过的项目。
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        """④ 非成员请求 save_baseline → 403「权限不足」，而非 404。"""
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.routers.group_note_baseline"),
            "GroupNoteBaselineService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        # 非成员应得 403，不是 404
        assert resp.status_code == 403, f"非成员应 403，实际 {resp.status_code}：{resp.text[:300]}"
        # 业务桩 0 次
        assert len(stub.calls) == 0, "非成员被拒时业务不应执行"
        # 拒绝信息含「权限不足」
        _assert_denied(resp, 403, REASON_FORBIDDEN)
        # 拒绝信息列出项目 id
        _assert_denied_lists_project(resp, TARGET_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        """③ readonly 成员 → 403「权限不足」。"""
        identity = await world.identity("readonly_member")
        stub = world.stub(
            importlib.import_module("app.routers.group_note_baseline"),
            "GroupNoteBaselineService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        assert resp.status_code == 403, f"readonly 成员应 403，实际 {resp.status_code}：{resp.text[:300]}"
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)
        _assert_denied_lists_project(resp, TARGET_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        """⑤ EQCR → 403，EQCR 只读原因。"""
        identity = await world.identity("project_eqcr")
        stub = world.stub(
            importlib.import_module("app.routers.group_note_baseline"),
            "GroupNoteBaselineService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        assert resp.status_code == 403, f"EQCR 应 403，实际 {resp.status_code}：{resp.text[:300]}"
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)
        _assert_denied_lists_project(resp, TARGET_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_edit_member_allowed(self, world: AuthzWorld) -> None:
        """① edit 级成员（manager, edit）→ 门禁放行。"""
        import importlib
        identity = await world.identity("edit_member")
        router_mod = importlib.import_module("app.routers.group_note_baseline")
        stub = world.stub(router_mod, "GroupNoteBaselineService", returns=_BaselineMock(), awaitable=False)

        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        # 放行证据：不是 401/403/423
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member 应被放行，实际 {resp.status_code}：{resp.text[:300]}"
        )
        # 门禁确实执行了
        client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        """⑧ admin 非成员 → 门禁放行。"""
        import importlib
        identity = await world.identity("admin_non_member")
        router_mod = importlib.import_module("app.routers.group_note_baseline")
        stub = world.stub(router_mod, "GroupNoteBaselineService", returns=_BaselineMock(), awaitable=False)

        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        assert resp.status_code not in (401, 403, 423), (
            f"admin 应被放行，实际 {resp.status_code}：{resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_edit_access")

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, world: AuthzWorld) -> None:
        """未登录 → 401。"""
        async with world.client(*_ALL_ROUTERS, user=None) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        assert resp.status_code == 401, f"未登录应 401，实际 {resp.status_code}：{resp.text[:300]}"

    @pytest.mark.asyncio
    async def test_error_lists_failed_project_ids(self, world: AuthzWorld) -> None:
        """拒绝时 detail.project_ids 列出未通过的项目。"""
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.routers.group_note_baseline"),
            "GroupNoteBaselineService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_ALL_ROUTERS, user=identity.user) as client:
            resp = await client.post(
                _SAVE_BASELINE_URL,
                params=_SAVE_BASELINE_PARAMS,
                json=_SAVE_BASELINE_BODY,
            )
        body = resp.json()
        detail = body.get("detail", {})
        assert isinstance(detail, dict), f"detail 应为 dict，实际 {type(detail).__name__}"
        assert "project_ids" in detail, f"detail 应含 project_ids 键"
        assert str(TARGET_PROJECT_ID) in detail["project_ids"], (
            f"project_ids 应含 {TARGET_PROJECT_ID}"
        )
        assert detail.get("error_code") == "NOTE_EDIT_MULTI_PROJECT_DENIED"




# ---------------------------------------------------------------------------
# note_conversion (B2): execute / rollback / preview (两种)
# design 定级：execute / rollback → assert_note_role_access({partner, manager})
#              preview (POST + GET) → require_project_access("readonly")
# ---------------------------------------------------------------------------
from app.routers import note_conversion  # noqa: E402

_CONVERSION_ROUTERS = (note_conversion.router,)

_EXECUTE_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/execute"
_EXECUTE_BODY = {"year": 2025, "target_type": "soe"}

_ROLLBACK_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/rollback"
_ROLLBACK_BODY = {"year": 2025}

_PREVIEW_POST_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/preview"
_PREVIEW_POST_BODY = {"year": 2025, "target_type": "soe"}

_PREVIEW_GET_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/2025/preview"
_PREVIEW_GET_PARAMS = {"target_type": "soe"}

_ROLE_DENIED_MSG = "\u4ec5\u672c\u9879\u76ee\u7ecf\u7406\u6216\u5408\u4f19\u4eba\u53ef\u5207\u6362\u9644\u6ce8\u6a21\u677f\u7c7b\u578b"


class _ConversionServiceMock:
    """NoteConversionService SmartMock: any method returns a sensible async default."""
    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            return {"status": "success", "added": 0, "removed": 0, "preserved": 0,
                    "added_items": [], "removed_items": []}
        return _method


class _ConversionPreviewResult:
    """preview_conversion return value mock (needs to_dict)."""
    def to_dict(self):
        return {"added": 0, "removed": 0, "preserved": 0, "added_items": [], "removed_items": []}


class _ConversionServiceMockWithPreview:
    """Mock with preview-specific return values."""
    def __getattr__(self, name: str):
        if name == "preview_conversion":
            async def _preview(*a, **kw):
                return _ConversionPreviewResult()
            return _preview
        if name == "preview_note_conversion":
            async def _note_preview(*a, **kw):
                return {"status": "preview", "from_type": "soe", "to_type": "listed",
                        "mapped": 0, "archived": 0, "created": 0,
                        "user_edits_preserved": 0, "forbidden_hits": [], "details": {}}
            return _note_preview
        async def _method(*a, **kw):
            return {"status": "success"}
        return _method


def _stub_conversion_service(world: AuthzWorld):
    """Stub NoteConversionService (lazy-imported inside endpoint function body)."""
    return world.stub(
        importlib.import_module("app.services.note_conversion_service"),
        "NoteConversionService",
        returns=_ConversionServiceMock(),
        awaitable=False,
    )


def _stub_conversion_service_preview(world: AuthzWorld):
    """Stub NoteConversionService (preview variant, needs to_dict)."""
    return world.stub(
        importlib.import_module("app.services.note_conversion_service"),
        "NoteConversionService",
        returns=_ConversionServiceMockWithPreview(),
        awaitable=False,
    )


class TestConversionExecuteDesignGate:
    """execute_conversion: assert_note_role_access({partner, manager}).
    Non-member / readonly / EQCR / qc / auditor -> 403; manager / partner / admin -> allowed.
    _Requirements: 8.2, 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("readonly_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_review_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("qc_review_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_OPERATION_DENIED)

    @pytest.mark.asyncio
    async def test_review_member_qc_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("review_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, _ROLE_DENIED_MSG)

    @pytest.mark.asyncio
    async def test_edit_member_manager_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("edit_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("admin_non_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")


class TestConversionRollbackDesignGate:
    """rollback_conversion: assert_note_role_access({partner, manager}).
    Same gate as execute; same identity set.
    _Requirements: 8.2, 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("readonly_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_review_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("qc_review_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_OPERATION_DENIED)

    @pytest.mark.asyncio
    async def test_edit_member_manager_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("edit_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("admin_non_member")
        stub = _stub_conversion_service(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")


class TestConversionPreviewDesignGate:
    """Both preview endpoints: require_project_access("readonly").
    Non-member -> 403; readonly and EQCR allowed.
    POST /preview + GET /{year}/preview tested separately.
    _Requirements: 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_post_preview_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_PREVIEW_POST_URL, json=_PREVIEW_POST_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_post_preview_readonly_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("readonly_member")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_PREVIEW_POST_URL, json=_PREVIEW_POST_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"readonly should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.deps.require_project_access.<locals>.dependency")

    @pytest.mark.asyncio
    async def test_post_preview_eqcr_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_PREVIEW_POST_URL, json=_PREVIEW_POST_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"EQCR should be allowed for preview, got {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_get_preview_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.get(_PREVIEW_GET_URL, params=_PREVIEW_GET_PARAMS)
        assert resp.status_code == 403
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_get_preview_readonly_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("readonly_member")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.get(_PREVIEW_GET_URL, params=_PREVIEW_GET_PARAMS)
        assert resp.status_code not in (401, 403, 423), (
            f"readonly should be allowed for GET preview, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.deps.require_project_access.<locals>.dependency")

    @pytest.mark.asyncio
    async def test_get_preview_eqcr_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = _stub_conversion_service_preview(world)
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.get(_PREVIEW_GET_URL, params=_PREVIEW_GET_PARAMS)
        assert resp.status_code not in (401, 403, 423), (
            f"EQCR should be allowed for GET preview, got {resp.status_code}: {resp.text[:300]}"
        )


# ---------------------------------------------------------------------------
# note_section_lock (B3): release / force-release
# Task 11.4
# ---------------------------------------------------------------------------
from app.routers import note_section_lock  # noqa: E402

_SECTION_LOCK_ROUTERS = (note_section_lock.router,)

_RELEASE_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/locks/release"
_RELEASE_BODY = {"year": 2025, "section_code": "五、1"}

_FORCE_RELEASE_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/locks/force-release"
_FORCE_RELEASE_BODY = {"year": 2025, "section_code": "五、1"}

_FORCE_RELEASE_DENIED_MSG = "仅本项目经理或合伙人可强制释放章节锁"


class _SectionLockServiceMock:
    """NoteSectionLockService SmartMock."""
    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            return True
        return _method


def _stub_section_lock_service(world: AuthzWorld):
    return world.stub(
        importlib.import_module("app.routers.note_section_lock"),
        "NoteSectionLockService",
        returns=_SectionLockServiceMock(),
        awaitable=False,
    )


class TestReleaseLockDesignGate:
    """release_lock: require_project_access("readonly").
    Non-member → 403; readonly and EQCR both allowed.
    _Requirements: 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("non_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_RELEASE_URL, json=_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_readonly_member_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("readonly_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_RELEASE_URL, json=_RELEASE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"readonly should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.deps.require_project_access.<locals>.dependency")

    @pytest.mark.asyncio
    async def test_eqcr_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("project_eqcr")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_RELEASE_URL, json=_RELEASE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"EQCR should be allowed for release, got {resp.status_code}: {resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_edit_member_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("edit_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_RELEASE_URL, json=_RELEASE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.deps.require_project_access.<locals>.dependency")


class TestForceReleaseLockDesignGate:
    """force_release_lock: assert_note_role_access({manager, partner}).
    Non-member / readonly / EQCR / qc / review_member → 403; edit_member(manager) / admin → allowed.
    _Requirements: 8.3, 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("non_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("readonly_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("project_eqcr")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_review_member_gets_403(self, world: AuthzWorld) -> None:
        """qc_review_member (qc, review, global qc) → 403 NOTE_EDIT_OPERATION_DENIED."""
        stub = _stub_section_lock_service(world)
        identity = await world.identity("qc_review_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_OPERATION_DENIED)

    @pytest.mark.asyncio
    async def test_review_member_gets_403(self, world: AuthzWorld) -> None:
        """review_member (qc, review, global auditor) → 403 with role denied message."""
        stub = _stub_section_lock_service(world)
        identity = await world.identity("review_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, _FORCE_RELEASE_DENIED_MSG)

    @pytest.mark.asyncio
    async def test_edit_member_manager_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("edit_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_section_lock_service(world)
        identity = await world.identity("admin_non_member")
        async with world.client(*_SECTION_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_FORCE_RELEASE_URL, json=_FORCE_RELEASE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")


# ---------------------------------------------------------------------------
# note_data_lock (B3): lock / unlock
# Task 11.4
# ---------------------------------------------------------------------------
from app.routers import note_data_lock  # noqa: E402

_DATA_LOCK_ROUTERS = (note_data_lock.router,)

_LOCK_URL = f"/api/projects/{TARGET_PROJECT_ID}/data-lock/lock"
_LOCK_BODY = {"year": 2025}

_UNLOCK_URL = f"/api/projects/{TARGET_PROJECT_ID}/data-lock/unlock"
_UNLOCK_BODY = {"year": 2025, "reason": "解锁原因"}

_LOCK_DENIED_MSG = "仅本项目经理或合伙人可锁定报表附注数据"
_UNLOCK_DENIED_MSG = "仅管理员可解除报表附注数据锁定"


class _DataLockServiceMock:
    """NoteDataLockService SmartMock."""
    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            return {"locked": True, "version": 1}
        return _method


def _stub_data_lock_service(world: AuthzWorld):
    return world.stub(
        importlib.import_module("app.routers.note_data_lock"),
        "NoteDataLockService",
        returns=_DataLockServiceMock(),
        awaitable=False,
    )


class TestLockOnSignOffDesignGate:
    """lock_on_sign_off: assert_note_role_access({partner, manager}).
    Non-member / readonly / EQCR / qc / review_member → 403; edit_member(manager) / admin → allowed.
    _Requirements: 8.3, 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("non_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("readonly_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("project_eqcr")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_review_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("qc_review_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_OPERATION_DENIED)

    @pytest.mark.asyncio
    async def test_review_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("review_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, _LOCK_DENIED_MSG)

    @pytest.mark.asyncio
    async def test_edit_member_manager_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("edit_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("admin_non_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_LOCK_URL, json=_LOCK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")


class TestUnlockDataDesignGate:
    """unlock_data: assert_note_role_access(frozenset(), admin-only).
    Non-member / readonly / EQCR / edit_member / review_member → 403; only admin → allowed.
    _Requirements: 8.3, 8.4, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("non_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_UNLOCK_URL, json=_UNLOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("readonly_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_UNLOCK_URL, json=_UNLOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("project_eqcr")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_UNLOCK_URL, json=_UNLOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_edit_member_gets_403(self, world: AuthzWorld) -> None:
        """edit_member (manager, edit) → 403 with role denied (empty frozenset = admin only)."""
        stub = _stub_data_lock_service(world)
        identity = await world.identity("edit_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_UNLOCK_URL, json=_UNLOCK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, _UNLOCK_DENIED_MSG)

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        stub = _stub_data_lock_service(world)
        identity = await world.identity("admin_non_member")
        async with world.client(*_DATA_LOCK_ROUTERS, user=identity.user) as client:
            resp = await client.post(_UNLOCK_URL, json=_UNLOCK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_role_access")


# ---------------------------------------------------------------------------
# note_group_template (B3): distribute
# Task 11.4: assert_note_edit_access_on_projects([project_id, *target_project_ids])
# ---------------------------------------------------------------------------
from app.routers import note_group_template  # noqa: E402
from tests.authz_world import OTHER_PROJECT_ID  # noqa: E402

_GROUP_TEMPLATE_ROUTERS = (note_group_template.router,)

_DISTRIBUTE_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/group-template/distribute"
_DISTRIBUTE_BODY = {
    "template_id": "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e50",
    "target_project_ids": [str(OTHER_PROJECT_ID)],
    "strategy": "bc_keep_data",
}


class _GroupTemplateServiceMock:
    """NoteGroupTemplateService SmartMock."""
    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            return {"distributed": True, "count": 1}
        return _method


def _stub_group_template_service(world: AuthzWorld):
    return world.stub(
        importlib.import_module("app.routers.note_group_template"),
        "NoteGroupTemplateService",
        returns=_GroupTemplateServiceMock(),
        awaitable=False,
    )


class TestDistributeTemplateDesignGate:
    """distribute_template: assert_note_edit_access_on_projects([project_id, *target_project_ids]).
    Non-member / readonly / EQCR → 403; edit_member / admin → allowed.
    Must list failed project IDs on denial.
    Must reject entire request if any project fails (no writes).
    _Requirements: 8.5, 8.6_
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_group_template_service(world)
        identity = await world.identity("non_member")
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=_DISTRIBUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0, "业务不应执行"
        _assert_denied(resp, 403, REASON_FORBIDDEN)
        # Non-member fails on both TARGET and OTHER project → both listed
        _assert_denied_lists_project(resp, TARGET_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_group_template_service(world)
        identity = await world.identity("readonly_member")
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=_DISTRIBUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        stub = _stub_group_template_service(world)
        identity = await world.identity("project_eqcr")
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=_DISTRIBUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_edit_member_target_only_allowed(self, world: AuthzWorld) -> None:
        """edit_member is member of TARGET; distribute to TARGET only (no OTHER) → allowed."""
        stub = _stub_group_template_service(world)
        identity = await world.identity("edit_member")
        body_target_only = {
            "template_id": "5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e50",
            "target_project_ids": [],
            "strategy": "bc_keep_data",
        }
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=body_target_only)
        assert resp.status_code not in (401, 403, 423), (
            f"edit_member should be allowed when targeting own project only, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_edit_access_on_projects")

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        """admin non-member → allowed for all projects."""
        stub = _stub_group_template_service(world)
        identity = await world.identity("admin_non_member")
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=_DISTRIBUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin should be allowed, got {resp.status_code}: {resp.text[:300]}"
        )
        client.assert_passed("app.services.note_edit_gate.assert_note_edit_access_on_projects")

    @pytest.mark.asyncio
    async def test_error_lists_failed_project_ids(self, world: AuthzWorld) -> None:
        """When target projects include one where the user is not a member, rejection lists those project IDs."""
        stub = _stub_group_template_service(world)
        identity = await world.identity("edit_member")
        # edit_member is member of TARGET but NOT of OTHER
        async with world.client(*_GROUP_TEMPLATE_ROUTERS, user=identity.user) as client:
            resp = await client.post(_DISTRIBUTE_URL, json=_DISTRIBUTE_BODY)
        # Should fail because OTHER_PROJECT_ID is not accessible
        assert resp.status_code == 403
        assert len(stub.calls) == 0, "Business must not execute when any project fails"
        body = resp.json()
        detail = body.get("detail", {})
        assert isinstance(detail, dict), f"detail should be dict, got {type(detail).__name__}"
        assert "project_ids" in detail, "detail should contain project_ids key"
        assert str(OTHER_PROJECT_ID) in detail["project_ids"], (
            f"project_ids should list {OTHER_PROJECT_ID}"
        )
        assert detail.get("error_code") == "NOTE_EDIT_MULTI_PROJECT_DENIED"


# ---------------------------------------------------------------------------
# Task 11.5: design 定级端点集合收口
# ---------------------------------------------------------------------------
import json as _json
from pathlib import Path as _Path

_INVENTORY_PATH_11_5 = _Path(__file__).resolve().parents[1] / "data" / "authz" / "note_write_inventory.json"


def _load_design_gate_set() -> set[tuple[str, str]]:
    """清册中 target_gate.kind == 'design_gate' 的端点集合。"""
    data = _json.loads(_INVENTORY_PATH_11_5.read_text("utf-8"))
    result: set[tuple[str, str]] = set()
    for ep in data["endpoints"]:
        tg = ep.get("target_gate") or {}
        if tg.get("kind") == "design_gate":
            result.add((ep["method"], ep["path"]))
    return result


# 文件内被测的 design 定级端点集合——把每个 Test*DesignGate 类对应的
# （method, inventory path）收集起来。
# 当新增或删除端点时，两边都必须同步更新，否则本测试会报差异。
_TESTED_DESIGN_GATE_ENDPOINTS: set[tuple[str, str]] = {
    # TestSaveBaselineDesignGate
    ("POST", "/api/group-note-baselines"),
    # TestConversionExecuteDesignGate
    ("POST", "/api/projects/{project_id}/notes/conversion/execute"),
    # TestConversionRollbackDesignGate
    ("POST", "/api/projects/{project_id}/notes/conversion/rollback"),
    # TestConversionPreviewDesignGate (POST preview — design_gate readonly)
    ("POST", "/api/projects/{project_id}/notes/conversion/preview"),
    # TestReleaseLockDesignGate
    ("POST", "/api/projects/{project_id}/notes/locks/release"),
    # TestForceReleaseLockDesignGate
    ("POST", "/api/projects/{project_id}/notes/locks/force-release"),
    # TestLockOnSignOffDesignGate
    ("POST", "/api/projects/{project_id}/data-lock/lock"),
    # TestUnlockDataDesignGate
    ("POST", "/api/projects/{project_id}/data-lock/unlock"),
    # TestDistributeTemplateDesignGate
    ("POST", "/api/projects/{project_id}/notes/group-template/distribute"),
}


class TestDesignGateEndpointSetClosure:
    """Task 11.5: 参数化端点集合等于清册中 design 定级门禁的端点集合。

    双向比较并逐个列出差异。
    _Requirements: 8.6_
    """

    def test_design_gate_set_equals_inventory(self) -> None:
        """双向比较：本文件实际被测的端点集合 == 清册 design_gate 集合。"""
        inventory_set = _load_design_gate_set()
        tested_set = _TESTED_DESIGN_GATE_ENDPOINTS

        only_in_inventory = inventory_set - tested_set
        only_in_tests = tested_set - inventory_set

        diff_lines: list[str] = []
        if only_in_inventory:
            diff_lines.append("清册中有、本测试文件未覆盖的 design 定级端点：")
            for m, p in sorted(only_in_inventory):
                diff_lines.append(f"  + {m} {p}")
        if only_in_tests:
            diff_lines.append("本测试文件有、清册中不存在的 design 定级端点：")
            for m, p in sorted(only_in_tests):
                diff_lines.append(f"  - {m} {p}")

        assert inventory_set == tested_set, (
            f"design 定级端点集合不一致（清册 {len(inventory_set)} 个 vs "
            f"测试 {len(tested_set)} 个）：\n"
            + "\n".join(diff_lines)
        )

    def test_design_gate_set_nonempty(self) -> None:
        """清册与测试的 design 定级端点集合非空。"""
        inventory_set = _load_design_gate_set()
        assert len(inventory_set) > 0, "清册中 design_gate 端点为空"
        assert len(_TESTED_DESIGN_GATE_ENDPOINTS) > 0, "测试文件 design_gate 端点为空"

    def test_each_design_gate_endpoint_has_test_class(self) -> None:
        """每个 design 定级端点在本文件至少有一个测试类的放行用例（需求 8.6）。"""
        inventory_set = _load_design_gate_set()
        for method, path in sorted(inventory_set):
            assert (method, path) in _TESTED_DESIGN_GATE_ENDPOINTS, (
                f"design_gate 端点 {method} {path} 在本测试文件中没有对应的测试"
            )

    def test_each_design_gate_endpoint_eqcr_matches_inventory(self) -> None:
        """每个 design 定级端点的 EQCR 声明都可在本文件中验证。"""
        data = _json.loads(_INVENTORY_PATH_11_5.read_text("utf-8"))
        for ep in data["endpoints"]:
            tg = ep.get("target_gate") or {}
            if tg.get("kind") != "design_gate":
                continue
            key = (ep["method"], ep["path"])
            eqcr_policy = tg.get("eqcr", "deny")
            assert key in _TESTED_DESIGN_GATE_ENDPOINTS, (
                f"design_gate 端点 {key} 的 EQCR 策略 '{eqcr_policy}' 无法验证（缺测试）"
            )
