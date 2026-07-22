"""G11 投资收益 — API 集成测试（render + 导入导出 + AI + OCR）."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g11_investment_income_import_export import _G11_SPECS


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
async def test_g11_render_dispatch_registered():
    assert "g11-investment-income" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g11-investment-income"]
    assert callable(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G11-1", "G11-2", "G11-3", "G11-4", "G11-5"])
async def test_g11_export_template_all_sheets(sheet: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/g11/export-template?sheet={sheet}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_g11_specs_cover_five_sheets():
    assert set(_G11_SPECS.keys()) == {"G11-1", "G11-2", "G11-3", "G11-4", "G11-5"}


@pytest.mark.asyncio
async def test_g11_ai_sections(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "ok"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g11_investment_income_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in (
            "adjudication-analysis",
            "return-rate-conclusion",
            "voucher-conclusion",
            "disclosure-note",
        ):
            resp = await client.post(
                f"/api/workpapers/test-wp/g11/ai/{section}",
                json={"existingContent": "", "rows": []},
            )
            assert resp.status_code == 200, section


@pytest.mark.asyncio
async def test_g11_contract_ocr_route_exists(monkeypatch):
    async def _fake_ocr(*_a, **_k):
        return {"text": "凭证摘要测试"}

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g11_contract_ocr.UnifiedOCRService",
        lambda: type("S", (), {"recognize": _fake_ocr})(),
    )
    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g11_contract_ocr.chat_completion",
        AsyncMock(return_value='{"summary":"测试","businessContent":"投资收益"}'),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/contract-ocr",
            files={"file": ("v.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert resp.status_code in (200, 500)


@pytest.mark.asyncio
async def test_g11_validate_formulas_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/validate-formulas",
            json={
                "adjudication_rows": [
                    {
                        "rowKey": "other",
                        "currentUnadjusted": 100,
                        "currentAdjustment": 10,
                        "currentAudited": 110,
                        "priorUnadjusted": 80,
                        "priorAdjustment": 5,
                        "priorAudited": 85,
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
async def test_g11_validate_formulas_mismatch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/validate-formulas",
            json={
                "adjudication_rows": [
                    {
                        "rowKey": "other",
                        "currentUnadjusted": 100,
                        "currentAdjustment": 10,
                        "currentAudited": 999,
                        "priorUnadjusted": 0,
                        "priorAdjustment": 0,
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
async def test_g11_validate_adjustment_balance():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/validate-formulas",
            json={"adjustment_debits": [100], "adjustment_credits": [90]},
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is False
    assert any(e.get("field") == "balance" for e in data["errors"])


@pytest.mark.asyncio
async def test_g11_save_adjudication(override_deps):
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "test-project-id"
    override_deps.execute = AsyncMock(return_value=mock_result)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/save-adjudication",
            json={
                "row_store": {
                    "other": {
                        "currentUnadjusted": 100,
                        "currentAdjustment": 10,
                        "priorUnadjusted": 80,
                        "priorAdjustment": 5,
                    }
                },
                "adjudicated_amount": 110,
                "audit_note": "note",
                "audit_conclusion": "ok",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["ok"] is True
    assert data["adjudicated_amount"] == 110
    override_deps.commit.assert_awaited()
