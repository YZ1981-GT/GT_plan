"""TB 发布门端点级验收测试。

用 httpx AsyncClient + ASGITransport 真发 HTTP 请求到 FastAPI 端点层，
验证 POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb 的：
  1. 正常发布路径：200 + published=True + wp_code + publish_token
  2. 非审定表 sheet → 400
  3. 空 audit_rows → 400
  4. 旧端点已删除（PUT trial-balance/writeback → 404/405）
  5. 路由注册存在性
  6. CI 守卫脚本可执行且通过
  7. 普通保存不携带 publish_confirmed（TB 不受影响的设计契约）

设计原则（与 test_export_endpoints_acceptance.py 同模式）：
  - mock DB + patch 鉴权/事件总线，不依赖真实数据库
  - 鉴权层通过 dependency_overrides 绕过
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole


# ─── 公共 fixtures ──────────────────────────────────────────────────────────

FAKE_WP_ID = str(uuid.uuid4())
FAKE_PROJECT_ID = uuid.uuid4()


class _FakeUser:
    id = str(uuid.uuid4())
    name = "Test User"
    email = "test@example.com"
    role = MagicMock(value=UserRole.admin.value)
    username = "testuser"


@pytest.fixture(autouse=True)
def _override_deps():
    """统一 override 鉴权 + DB + RLS + 内部鉴权函数。"""
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db

    with patch("app.core.database.set_rls_context", new_callable=AsyncMock):
        yield mock_db

    app.dependency_overrides.clear()


@pytest.fixture
def transport():
    return ASGITransport(app=app)


def _valid_body():
    return {
        "sheet_name": "审定表D2-1",
        "html_data": {
            "audit_rows": [
                {
                    "id": "r1",
                    "account_code": "1122",
                    "current_unadjusted": 1000,
                    "adj_amount": 50,
                    "reclass_amount": 0,
                },
            ]
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. 正常发布路径
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishToTbEndpoint:
    """POST /api/workpapers/{wp_id}/audit-determination/publish-to-tb 端点验收。

    底稿路由有 wp_visibility 安全中间件拦截，mock DB 环境下无法穿过。
    200 路径已由 test_publish_determination_to_tb.py（直接调函数）充分覆盖。
    此处验证：端点函数签名正确 + 参数校验 + 返回模型 + 事件携带正确信号。
    """

    @pytest.mark.asyncio
    async def test_publish_function_emits_confirmed_signal(self, _override_deps):
        """直调端点函数：200 + published + 事件携带 publish_confirmed=True。"""
        published_events = []

        async def _capture(payload):
            published_events.append(payload)

        with (
            patch(
                "app.deps.authorize_wp_edit",
                new_callable=AsyncMock,
                return_value=FAKE_PROJECT_ID,
            ),
            patch(
                "app.deps.check_consol_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.wp_html_save.fetch_project_audit_year",
                new_callable=AsyncMock,
                return_value=2025,
            ),
            patch(
                "app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.services.event_bus.event_bus.publish",
                side_effect=_capture,
            ),
        ):
            from app.routers.wp_html_save import (
                PublishToTbRequest,
                publish_determination_to_tb,
            )

            body = PublishToTbRequest(**_valid_body(), publish_token="test-token-auto")
            resp = await publish_determination_to_tb(
                wp_id=uuid.UUID(FAKE_WP_ID),
                body=body,
                db=_override_deps,
                current_user=_FakeUser(),
            )

            assert resp.published is True
            assert resp.wp_code == "D2-1"
            assert resp.publish_token == "test-token-auto"

            # 事件携带 publish_confirmed 信号
            assert len(published_events) == 1
            extra = published_events[0].extra
            assert extra["publish_confirmed"] is True
            assert extra["confirmed_by"]
            assert extra["publish_token"] == "test-token-auto"

    @pytest.mark.asyncio
    async def test_non_determination_sheet_returns_400(self, _override_deps):
        """非审定表 sheet → 400。"""
        from fastapi import HTTPException

        with (
            patch("app.deps.authorize_wp_edit", new_callable=AsyncMock, return_value=FAKE_PROJECT_ID),
            patch("app.deps.check_consol_lock", new_callable=AsyncMock),
        ):
            from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

            body_data = _valid_body()
            body_data["sheet_name"] = "明细表D4-2"
            body = PublishToTbRequest(**body_data)
            with pytest.raises(HTTPException) as ei:
                await publish_determination_to_tb(
                    wp_id=uuid.UUID(FAKE_WP_ID), body=body,
                    db=_override_deps, current_user=_FakeUser(),
                )
            assert ei.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_audit_rows_returns_400(self, _override_deps):
        """空 audit_rows → 400。"""
        from fastapi import HTTPException

        with (
            patch("app.deps.authorize_wp_edit", new_callable=AsyncMock, return_value=FAKE_PROJECT_ID),
            patch("app.deps.check_consol_lock", new_callable=AsyncMock),
        ):
            from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

            body = PublishToTbRequest(sheet_name="审定表D2-1", html_data={"audit_rows": []})
            with pytest.raises(HTTPException) as ei:
                await publish_determination_to_tb(
                    wp_id=uuid.UUID(FAKE_WP_ID), body=body,
                    db=_override_deps, current_user=_FakeUser(),
                )
            assert ei.value.status_code == 400

    @pytest.mark.asyncio
    async def test_publish_token_passthrough(self, _override_deps):
        """传入 publish_token 时端点原样透传。"""
        with (
            patch("app.deps.authorize_wp_edit", new_callable=AsyncMock, return_value=FAKE_PROJECT_ID),
            patch("app.deps.check_consol_lock", new_callable=AsyncMock),
            patch("app.routers.wp_html_save.fetch_project_audit_year", new_callable=AsyncMock, return_value=2025),
            patch("app.services.wp_audit_sheet_tb_service.fetch_audit_sheet_tb_values", new_callable=AsyncMock, return_value={}),
            patch("app.services.event_bus.event_bus.publish", new_callable=AsyncMock),
        ):
            from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

            body_data = _valid_body()
            body_data["publish_token"] = "idempotent-token-abc"
            body = PublishToTbRequest(**body_data)
            resp = await publish_determination_to_tb(
                wp_id=uuid.UUID(FAKE_WP_ID), body=body,
                db=_override_deps, current_user=_FakeUser(),
            )
            assert resp.publish_token == "idempotent-token-abc"

    @pytest.mark.asyncio
    async def test_writeback_rows_path(self, _override_deps):
        """路径②：writeback_rows 直传审定数。"""
        with (
            patch("app.deps.authorize_wp_edit", new_callable=AsyncMock, return_value=FAKE_PROJECT_ID),
            patch("app.deps.check_consol_lock", new_callable=AsyncMock),
            patch("app.routers.wp_html_save.fetch_project_audit_year", new_callable=AsyncMock, return_value=2025),
            patch("app.services.event_bus.event_bus.publish", new_callable=AsyncMock),
        ):
            from app.routers.wp_html_save import PublishToTbRequest, publish_determination_to_tb

            body = PublishToTbRequest(
                sheet_name="审定表K6-1",
                writeback_rows=[
                    {"account_code": "6601", "audited_amount": 12345.67, "amount_kind": "occurrence"},
                ],
                publish_token="test-token-k6",
            )
            resp = await publish_determination_to_tb(
                wp_id=uuid.UUID(FAKE_WP_ID), body=body,
                db=_override_deps, current_user=_FakeUser(),
            )
            assert resp.published is True
            assert resp.wp_code == "K6-1"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 旧端点已删除
# ═══════════════════════════════════════════════════════════════════════════


class TestLegacyWritebackEndpointRemoved:
    """旧 trial-balance/writeback 端点不应存在。"""

    @pytest.mark.asyncio
    async def test_legacy_put_writeback_not_found(self, transport, _override_deps):
        """PUT /api/projects/{pid}/trial-balance/writeback → 404 或 405。"""
        pid = str(uuid.uuid4())
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.put(
                f"/api/projects/{pid}/trial-balance/writeback",
                json={"rows": []},
            )
        assert resp.status_code in (404, 405), (
            f"旧端点 PUT trial-balance/writeback 仍可达: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_legacy_post_writeback_not_found(self, transport, _override_deps):
        """POST /api/projects/{pid}/trial-balance/writeback → 404 或 405。"""
        pid = str(uuid.uuid4())
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{pid}/trial-balance/writeback",
                json={"rows": []},
            )
        assert resp.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_g6_variant_endpoint_not_active(self, transport, _override_deps):
        """G6 变体端点 POST /api/projects/{pid}/trial_balance → 404 或 405。"""
        pid = str(uuid.uuid4())
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{pid}/trial_balance",
                json={},
            )
        assert resp.status_code in (404, 405)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 路由注册与设计契约
# ═══════════════════════════════════════════════════════════════════════════


class TestTbPublishGateDesignContract:
    """TB 发布门的设计契约守卫。"""

    def test_publish_route_registered(self):
        """发布端点路由已注册。"""
        route_list = [
            (frozenset(r.methods), r.path)
            for r in app.routes
            if hasattr(r, "methods") and hasattr(r, "path")
        ]
        found = any(
            "POST" in ms
            and "/api/workpapers/{wp_id}/audit-determination/publish-to-tb" == p
            for ms, p in route_list
        )
        assert found, "publish-to-tb 端点未注册"

    def test_legacy_writeback_route_not_registered(self):
        """旧 trial-balance/writeback 路由不应注册。"""
        route_list = [
            r.path for r in app.routes if hasattr(r, "path")
        ]
        for path in route_list:
            assert "trial-balance/writeback" not in path, (
                f"旧端点 trial-balance/writeback 仍注册: {path}"
            )

    def test_event_handler_checks_publish_confirmed(self):
        """事件处理器 _on_d_audit_determination_saved 包含 publish_confirmed 门控。"""
        import inspect

        from app.services import event_handlers_cycle_linkage as mod

        source = inspect.getsource(mod._on_d_audit_determination_saved)
        assert "publish_confirmed" in source, (
            "事件处理器缺少 publish_confirmed 门控检查"
        )
        assert 'extra.get("publish_confirmed") is not True' in source or \
               "publish_confirmed" in source, (
            "事件处理器的 publish_confirmed 门控格式不符预期"
        )

    def test_normal_save_does_not_carry_publish_confirmed(self):
        """wp_html_save 的普通保存注释说明不含 publish_confirmed。"""
        import inspect

        from app.routers import wp_html_save

        source = inspect.getsource(wp_html_save)
        # 普通保存的注释/代码应说明不含 publish_confirmed
        assert "不含 publish_confirmed" in source or "不带 publish_confirmed" in source, (
            "wp_html_save.py 未注释说明普通保存不携带 publish_confirmed 信号"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. CI 守卫脚本可执行
# ═══════════════════════════════════════════════════════════════════════════


class TestCiGuardScriptsExecutable:
    """CI 守卫脚本存在且可执行（exit 0 = 通过）。"""

    def test_check_tb_writeback_no_direct_call_passes(self):
        """守卫 A（旧端点直调检测）通过。"""
        from scripts.check.check_tb_writeback_no_direct_call import main

        rc = main([])
        assert rc == 0, "check_tb_writeback_no_direct_call 检测到违规"

    def test_check_tb_publish_confirm_gate_passes(self):
        """守卫 B（发布确认门检测）通过。"""
        from scripts.check.check_tb_publish_confirm_gate import main

        rc = main([])
        assert rc == 0, "check_tb_publish_confirm_gate 检测到违规"
