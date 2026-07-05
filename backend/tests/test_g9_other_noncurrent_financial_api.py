"""G9 其他非流动金融资产 — API 集成测试."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g9_other_noncurrent_financial_import_export import _G9_SPECS


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
async def test_g9_render_dispatch_registered():
    assert "g9-other-noncurrent-financial" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g9-other-noncurrent-financial"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G9-2", "G9-3", "G9-4", "G9-5", "G9-6"])
async def test_g9_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/workpapers/test-wp/g9/export-template?sheet={sheet}",
            headers={"Authorization": "Bearer test"},
        )
    assert resp.status_code == 200
    assert sheet in _G9_SPECS


@pytest.mark.asyncio
async def test_g9_ai_sections():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in (
            "adjudication-analysis",
            "fair-value-conclusion",
            "l3-reconciliation-conclusion",
            "voucher-conclusion",
            "disclosure-section",
        ):
            resp = await client.post(
                f"/api/workpapers/test-wp/g9/ai/{section}",
                headers={"Authorization": "Bearer test"},
                json={"existingContent": "", "rows": []},
            )
            assert resp.status_code in (200, 500, 504), section


@pytest.mark.asyncio
async def test_g9_validate_formulas_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g9/validate-formulas",
            json={
                "adjudication_rows": [],
                "l3_rows": [],
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
async def test_g9_validate_formulas_detects_errors():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g9/validate-formulas",
            json={
                "adjudication_rows": [{
                    "rowKey": "row1",
                    "openingUnadjusted": 100,
                    "openingAJE": 10,
                    "openingRJE": 0,
                    "openingAdjusted": 50,
                    "closingUnadjusted": 0,
                    "closingAJE": 0,
                    "closingRJE": 0,
                    "closingAdjusted": 0,
                }],
                "l3_rows": [{
                    "rowId": "l3-1",
                    "openingFairValue": 100,
                    "purchaseAmount": 0,
                    "disposalAmount": 0,
                    "transferIn": 0,
                    "transferOut": 0,
                    "fvChangePL": 0,
                    "fvChangeOCI": 0,
                    "interestIncome": 0,
                    "impairmentLoss": 0,
                    "otherChanges": 0,
                    "closingFairValue": 200,
                    "reportedClosing": 0,
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
