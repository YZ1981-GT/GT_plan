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

from authz_world import (
    TARGET_PROJECT_ID,
    AuthzWorld,
    Identity,
    sqlite_world,
)

from app.services.note_edit_gate import (
    REASON_EQCR_READONLY,
    REASON_FORBIDDEN,
    REASON_MULTI_PROJECT_DENIED_PREFIX,
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
# 闄勬敞妯℃澘鎻愬瀷杞崲绔偣锛坉esign 瀹氱骇锛?
# note_conversion.py: preview (readonly) / execute & rollback (assert_note_role_access)
# ---------------------------------------------------------------------------

# 瀵煎叆杞崲璺敱
from app.routers import note_conversion  # noqa: E402

_CONVERSION_ROUTERS = (note_conversion.router,)

# --- 杈呭姪 ---

class _ConversionServiceMock:
    """NoteConversionService 鐨?SmartMock锛氫换浣曟柟娉曞畨鍏ㄨ繑鍥炲悎鐞嗗€笺€?""
    def __getattr__(self, name: str):
        async def _method(*args, **kwargs):
            if "preview" in name:
                # preview_conversion 杩斿洖 .to_dict() 鐨勫璞?
                class _R:
                    def to_dict(self):
                        return {"added": 0, "removed": 0, "preserved": 0,
                                "added_items": [], "removed_items": []}
                return _R()
            return {"status": "success"}
        return _method


_EXECUTE_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/execute"
_EXECUTE_BODY = {"year": 2025, "target_type": "soe"}
_ROLLBACK_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/rollback"
_ROLLBACK_BODY = {"year": 2025}
_PREVIEW_POST_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/preview"
_PREVIEW_POST_BODY = {"year": 2025, "target_type": "soe"}
_PREVIEW_GET_URL = f"/api/projects/{TARGET_PROJECT_ID}/notes/conversion/2025/preview?target_type=soe"


# --- preview (POST /preview 鍙婁 GET /{year}/preview) 锛歳equire_project_access("readonly") ---

class TestConversionPreviewReadonly:
    """杞崲棰勮瑙?棰勮绔偣鏀逛负 readonly 绾э紝readonly 鎴愬憳鍜?EQCR 搴旀斁琛屻€?""

    @pytest.mark.asyncio
    async def test_preview_post_non_member_403(self, world: AuthzWorld) -> None:
        """闈炴垚鍛?POST /preview 鈫?403"""
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_PREVIEW_POST_URL, json=_PREVIEW_POST_BODY)
        assert resp.status_code == 403, f"闈炴垚鍛樺簲 403锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_preview_get_non_member_403(self, world: AuthzWorld) -> None:
        """闈炴垚鍛?GET /{year}/preview 鈫?403"""
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.get(_PREVIEW_GET_URL)
        assert resp.status_code == 403, f"闈炴垚鍛樺簲 403锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_preview_post_readonly_allowed(self, world: AuthzWorld) -> None:
        """readonly 鎴愬憳 POST /preview 鈫?鏀捐"""
        identity = await world.identity("readonly_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_PREVIEW_POST_URL, json=_PREVIEW_POST_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"readonly 鎴愬憳搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_preview_get_eqcr_allowed(self, world: AuthzWorld) -> None:
        """EQCR GET /{year}/preview 鈫?鏀捐锛堝彧璇荤鐐癸級"""
        identity = await world.identity("project_eqcr")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.get(_PREVIEW_GET_URL)
        assert resp.status_code not in (401, 403, 423), (
            f"EQCR 搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )


# --- execute / rollback: assert_note_role_access({partner, manager}) ---

from app.services.note_edit_gate import REASON_OPERATION_DENIED  # noqa: E402

_DENIED_MESSAGE_CONVERSION = "浠呮湰椤圭洰缁忕悊鎴栧悎浼欎汉鍙垏鎹㈤檮娉ㄦā鏉跨被鍨?


class TestConversionExecuteDesignGate:
    """execute_conversion 绔偣閴存潈锛歛ssert_note_role_access({partner, manager})銆?
    闈炴垚鍛?/ readonly / EQCR / 璐ㄦ帶 / 瀹¤鍛?鈫?403锛涚粡鐞?/ 鍚堜紮浜?/ admin 鈫?鏀捐銆?
    """

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403, f"闈炴垚鍛樺簲 403锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_readonly_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("readonly_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_member_gets_403(self, world: AuthzWorld) -> None:
        """璐ㄦ帶锛坬c, review锛?鈫?403锛氶€氳繃闄勬敞缂栬緫闂ㄧ浣嗚鑹查檺瀹氭嫆缁?""
        identity = await world.identity("qc_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403, f"璐ㄦ帶搴?403锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        assert len(stub.calls) == 0
        _assert_denied_exact(resp, 403, _DENIED_MESSAGE_CONVERSION)

    @pytest.mark.asyncio
    async def test_auditor_member_gets_403(self, world: AuthzWorld) -> None:
        """瀹¤鍛橈紙auditor, edit锛?鈫?403锛氶€氳繃缂栬緫闂ㄧ浣嗚鑹查檺瀹氭嫆缁?""
        identity = await world.identity("auditor_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code == 403, f"瀹¤鍛樺簲 403锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        assert len(stub.calls) == 0
        _assert_denied_exact(resp, 403, _DENIED_MESSAGE_CONVERSION)

    @pytest.mark.asyncio
    async def test_manager_allowed(self, world: AuthzWorld) -> None:
        """缁忕悊锛坢anager, edit锛?鈫?鏀捐"""
        identity = await world.identity("edit_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"缁忕悊搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_partner_allowed(self, world: AuthzWorld) -> None:
        """鍚堜紮浜猴紙partner, edit锛?鈫?鏀捐"""
        identity = await world.identity("partner_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"鍚堜紮浜哄簲鏀捐锛屽疄闄?{resp.status_code}锛歿resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        """admin 闈炴垚鍛?鈫?鏀捐"""
        identity = await world.identity("admin_non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_EXECUTE_URL, json=_EXECUTE_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin 搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )


class TestConversionRollbackDesignGate:
    """rollback_conversion 绔偣閴存潈锛氫笌 execute 鍚岃鍒欍€?""

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_FORBIDDEN)

    @pytest.mark.asyncio
    async def test_eqcr_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("project_eqcr")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied(resp, 403, REASON_EQCR_READONLY)

    @pytest.mark.asyncio
    async def test_qc_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("qc_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied_exact(resp, 403, _DENIED_MESSAGE_CONVERSION)

    @pytest.mark.asyncio
    async def test_auditor_member_gets_403(self, world: AuthzWorld) -> None:
        identity = await world.identity("auditor_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=None,
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code == 403
        assert len(stub.calls) == 0
        _assert_denied_exact(resp, 403, _DENIED_MESSAGE_CONVERSION)

    @pytest.mark.asyncio
    async def test_manager_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("edit_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"缁忕悊搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )

    @pytest.mark.asyncio
    async def test_admin_allowed(self, world: AuthzWorld) -> None:
        identity = await world.identity("admin_non_member")
        stub = world.stub(
            importlib.import_module("app.services.note_conversion_service"),
            "NoteConversionService",
            returns=_ConversionServiceMock(),
            awaitable=False,
        )
        async with world.client(*_CONVERSION_ROUTERS, user=identity.user) as client:
            resp = await client.post(_ROLLBACK_URL, json=_ROLLBACK_BODY)
        assert resp.status_code not in (401, 403, 423), (
            f"admin 搴旀斁琛岋紝瀹為檯 {resp.status_code}锛歿resp.text[:300]}"
        )
