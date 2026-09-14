"""H10 资产处置损益 — API 集成测试（render + 导入导出 + validate）."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._h10_asset_disposal_income_import_export import _H10_SPECS


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


@pytest.mark.asyncio
async def test_h10_render_dispatch_registered():
    assert "h10-asset-disposal-income" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["h10-asset-disposal-income"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["H10-2", "H10-3"])
async def test_h10_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/h10/export-template?sheet={sheet}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_h10_specs_cover_two_sheets():
    assert set(_H10_SPECS.keys()) == {"H10-2", "H10-3"}


@pytest.mark.asyncio
async def test_h10_validate_formulas_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/h10/validate-formulas",
            json={
                "adjudication_rows": [
                    {
                        "rowKey": "fixed_asset",
                        "currentUnadjusted": 100,
                        "currentAje": 10,
                        "currentRje": 5,
                        "currentAudited": 115,
                        "priorUnadjusted": 80,
                        "priorAje": 0,
                        "priorRje": 0,
                        "priorAudited": 80,
                    }
                ],
                "detail_rows": [],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_h10_validate_formulas_mismatch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/h10/validate-formulas",
            json={
                "adjudication_rows": [
                    {
                        "rowKey": "other",
                        "currentUnadjusted": 100,
                        "currentAje": 10,
                        "currentRje": 5,
                        "currentAudited": 999,
                        "priorUnadjusted": 0,
                        "priorAje": 0,
                        "priorRje": 0,
                        "priorAudited": 0,
                    }
                ],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is False
    assert len(data["errors"]) >= 1


@pytest.mark.asyncio
async def test_h10_validate_adjustment_balance():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/h10/validate-formulas",
            json={"adjustment_debits": [100], "adjustment_credits": [90]},
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is False
    assert any(e.get("field") == "balance" for e in data["errors"])


@pytest.mark.asyncio
async def test_h10_ai_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/h10/ai/unknown-section",
            json={"existingContent": ""},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_h10_save_adjudication(override_deps):
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "test-project-id"
    override_deps.execute = AsyncMock(return_value=mock_result)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/h10/save-adjudication",
            json={
                "row_store": {
                    "other": {
                        "currentUnadjusted": 100,
                        "currentAje": 10,
                        "currentRje": 5,
                        "priorUnadjusted": 80,
                        "priorAje": 0,
                        "priorRje": 0,
                    }
                },
                "adjudicated_amount": 115,
                "audit_note": "note",
                "audit_conclusion": "ok",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is True
    assert data["adjudicated_amount"] == 115
    override_deps.commit.assert_awaited()
