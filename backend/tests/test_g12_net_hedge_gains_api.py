"""G12 净敞口套期收益 — router 导入与注册 smoke 测试."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db


_COMPONENT = "g12-net-hedge-gains"


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


def test_g12_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])


def test_g12_import_export_router_import():
    from app.routers.wp_render_strategies._g12_net_hedge_gains_import_export import (
        _G12_SPECS,
        router,
    )

    assert router is not None
    assert set(_G12_SPECS.keys()) == {"G12-2", "G12-3", "G12-4", "G12-5", "G12-6"}


def test_g12_ai_sections():
    from app.routers.wp_render_strategies._g12_net_hedge_gains_ai import _PROMPTS

    assert set(_PROMPTS.keys()) == {
        "adjudication-analysis",
        "hedge-effectiveness-conclusion",
        "net-position-conclusion",
        "voucher-conclusion",
    }


def test_g12_service_import():
    from app.routers.wp_render_strategies._g12_net_hedge_gains_service import (
        G12NetHedgeGainsService,
    )

    svc = G12NetHedgeGainsService()
    assert svc.calc_hedge_ineffectiveness(10, -5) == 15


def test_g12_render_module_constants():
    """科目定位改走规格声明，`_G12_ACCOUNT_PREFIX` 常量已删。

    `IS-014 净敞口套期收益` 的 formula 为 None → 兜底 `6103`。
    🔴 公式预设曾错写 `6115`（= 资产处置损益，H10 的科目），故断言排除它。
    """
    from app.routers.wp_render_strategies import _g12_net_hedge_gains as mod

    assert not hasattr(mod, "_G12_ACCOUNT_PREFIX"), "旧硬编码前缀常量不得复活"
    assert tuple(mod.G12_ACCOUNT_SPEC.fallback_gross) == ("6103",)
    assert "6115" not in tuple(mod.G12_ACCOUNT_SPEC.fallback_gross)
    assert mod._ADJUDICATED_ITEM_ID == "G12-1-adjudicated-amount"


@pytest.mark.asyncio
async def test_g12_export_template_g12_2():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g12/export-template?sheet=G12-2",
        )
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_g12_export_template_unknown_sheet():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g12/export-template?sheet=G12-99",
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_g12_ai_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g12/ai/unknown-section",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 404
