"""G11 导入导出 — 单元测试."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies._cycle_import_export_common import build_workbook_template, parse_upload_xlsx
from app.routers.wp_render_strategies._g11_investment_income_import_export import _G11_SPECS, _build_g11_5_workbook


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
async def test_g11_export_template_g11_1():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workpapers/test-wp/g11/export-template?sheet=G11-1")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_g11_export_template_g11_2():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workpapers/test-wp/g11/export-template?sheet=G11-2")
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_g11_export_template_g11_5_multi_sheet():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workpapers/test-wp/g11/export-template?sheet=G11-5")
    assert resp.status_code == 200


def test_g11_1_headers_match():
    sp = _G11_SPECS["G11-1"]
    assert "行键" in sp["headers"]
    assert "本期未审数" in sp["headers"]
    assert len(sp["headers"]) == len(sp["field_keys"])


def test_g11_2_headers_match_xlsx():
    sp = _G11_SPECS["G11-2"]
    assert "本期未审数" in sp["headers"]
    assert "变动原因/索引号" in sp["headers"]
    assert len(sp["headers"]) == len(sp["field_keys"])


def test_g11_5_workbook_has_three_segments():
    wb = _build_g11_5_workbook([], template_only=True)
    names = wb.sheetnames
    assert any("凭证基础" in n for n in names)
    assert any("核对内容" in n for n in names)
    assert any("结论" in n for n in names)


def test_g11_4_opening_closing_parse():
    sp = _G11_SPECS["G11-4"]
    wb = build_workbook_template("G11-4", sp["headers"], title=sp.get("title"))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    headers, rows = parse_upload_xlsx(buf.read(), sp["headers"], header_row=2)
    assert "本期期初余额" in headers
    assert "上期期末余额" in headers


@pytest.mark.asyncio
async def test_g11_ai_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g11/ai/unknown-section",
            json={"existingContent": ""},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_g11_ai_sections_registered(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "测试结论"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g11_investment_income_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for section in ("adjudication-analysis", "return-rate-conclusion", "voucher-conclusion"):
            resp = await client.post(
                f"/api/workpapers/test-wp/g11/ai/{section}",
                json={"existingContent": "", "rows": []},
            )
            assert resp.status_code == 200, section
            body = resp.json()
            payload = body.get("data", body)
            assert payload.get("content")
