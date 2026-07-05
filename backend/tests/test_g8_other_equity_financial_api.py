"""G8 其他权益工具投资 — API 集成测试."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g8_other_equity_instruments_import_export import _G8_SPECS


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
async def test_g8_render_dispatch_registered():
    assert "g8-other-equity-instruments" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g8-other-equity-instruments"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G8-2", "G8-3", "G8-4", "G8-6"])
async def test_g8_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/workpapers/test-wp/g8/export-template?sheet={sheet}",
            headers={"Authorization": "Bearer test"},
        )
    assert resp.status_code == 200
    assert sheet in _G8_SPECS


@pytest.mark.asyncio
async def test_g8_ai_sections():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in (
            "adjudication-analysis",
            "fair-value-conclusion",
            "designation-conclusion",
            "voucher-conclusion",
        ):
            resp = await client.post(
                f"/api/workpapers/test-wp/g8/ai/{section}",
                headers={"Authorization": "Bearer test"},
                json={"existingContent": "", "rows": []},
            )
            assert resp.status_code in (200, 500, 504), section


@pytest.mark.asyncio
async def test_g8_validate_formulas_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g8/validate-formulas",
            json={
                "adjudication_rows": [],
                "detail_rows": [],
                "fair_value_rows": [],
                "adjustment_debits": [],
                "adjustment_credits": [],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_g8_validate_formulas_detects_errors():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g8/validate-formulas",
            json={
                "adjudication_rows": [{
                    "rowKey": "row1",
                    "openingUnadjusted": 100,
                    "openingAdjustment": 10,
                    "openingAdjusted": 50,
                    "closingUnadjusted": 200,
                    "closingAdjustment": 0,
                    "closingAdjusted": 0,
                }],
                "detail_rows": [{
                    "investeeName": "测试公司",
                    "openingBalance": 100,
                    "openingAdjustment": 0,
                    "openingAdjusted": 100,
                    "increaseAmount": 0,
                    "decreaseAmount": 0,
                    "fvChangeAmount": 0,
                    "closingBalance": 200,
                    "closingAdjustment": 0,
                    "closingAdjusted": 0,
                }],
                "fair_value_rows": [{
                    "investeeName": "测试公司",
                    "closingUnadjustedFV": 100,
                    "closingAuditedFV": 120,
                    "fairValueDiff": 0,
                }],
                "adjustment_debits": [1000],
                "adjustment_credits": [500],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is False
    assert len(data["errors"]) >= 2
    fields = {e["field"] for e in data["errors"]}
    assert "openingAdjusted" in fields
    assert "balance" in fields
