"""G13 公允价值变动收益 — router 导入与注册 smoke 测试."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db

_COMPONENT = "g13-fair-value-changes"


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


def test_g13_renderer_dispatch():
    from app.routers.wp_render_strategies import RENDERER_DISPATCH

    assert _COMPONENT in RENDERER_DISPATCH
    assert callable(RENDERER_DISPATCH[_COMPONENT])


def test_g13_import_export_router_import():
    from app.routers.wp_render_strategies._g13_fair_value_changes_import_export import (
        _G13_SPECS,
        router,
    )

    assert router is not None
    assert set(_G13_SPECS.keys()) == {"G13-2", "G13-3"}


def test_g13_ai_sections():
    from app.routers.wp_render_strategies._g13_fair_value_changes_ai import _PROMPTS

    assert set(_PROMPTS.keys()) == {"adjudication-analysis", "fv-change-conclusion"}


def test_g13_service_import():
    from app.routers.wp_render_strategies._g13_fair_value_changes_service import (
        G13FairValueChangesService,
    )

    svc = G13FairValueChangesService()
    assert svc.calc_fv_change(100, 120) == 20


@pytest.mark.asyncio
async def test_g13_export_template_g13_2():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g13/export-template?sheet=G13-2",
        )
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers.get("content-type", "")
