"""G10 交易性金融负债 — API 集成测试（render + 导入导出）."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g10_trading_financial_liabilities_import_export import _G10_SPECS


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
async def test_g10_render_dispatch_registered():
    assert "g10-trading-financial-liabilities" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g10-trading-financial-liabilities"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G10-2", "G10-3", "G10-5", "G10-6", "G10-7"])
async def test_g10_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/g10/export-template?sheet={sheet}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_g10_specs_cover_five_sheets():
    assert set(_G10_SPECS.keys()) == {"G10-2", "G10-3", "G10-5", "G10-6", "G10-7"}


@pytest.mark.asyncio
async def test_g10_validate_formulas_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g10/validate-formulas",
            json={
                "adjudication_rows": [{
                    "rowKey": "init_trading_liability",
                    "openingUnadjusted": 100,
                    "openingAdjustment": 0,
                    "openingAdjusted": 100,
                    "periodCredit": 50,
                    "periodDebit": 20,
                    "closingUnadjusted": 130,
                    "closingAdjustment": 0,
                    "closingAdjusted": 130,
                }],
                "l3_rows": [],
                "adjustment_debits": [100],
                "adjustment_credits": [100],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_g10_validate_formulas_mismatch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g10/validate-formulas",
            json={
                "adjudication_rows": [{
                    "rowKey": "init_trading_liability",
                    "openingUnadjusted": 100,
                    "openingAdjustment": 0,
                    "openingAdjusted": 100,
                    "periodCredit": 50,
                    "periodDebit": 20,
                    "closingUnadjusted": 999,
                    "closingAdjustment": 0,
                    "closingAdjusted": 999,
                }],
                "adjustment_debits": [50],
                "adjustment_credits": [100],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is False
    assert len(data["errors"]) >= 1


@pytest.mark.asyncio
async def test_g10_ai_sections(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "ok"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g10_trading_financial_liabilities_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in (
            "adjudication-analysis",
            "classification-conclusion",
            "fair-value-conclusion",
            "derivative-conclusion",
            "voucher-conclusion",
        ):
            resp = await client.post(
                f"/api/workpapers/test-wp/g10/ai/{section}",
                json={"existingContent": "", "rows": []},
            )
            assert resp.status_code == 200, section
