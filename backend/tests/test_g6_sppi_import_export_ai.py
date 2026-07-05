"""G6 其他债权投资(SPPI组) — 导入导出 + AI 端点集成测试.

Tests:
  - 4表导出模板端点 (G6-5/G6-6/G6-9/G6-10)
  - 导出数据(空工作簿)
  - 导入数据(有效xlsx / 无效格式 / 无效sheet)
  - AI 4 section端点 + 无效section
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.core.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    """Override DB and auth dependencies for all tests."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    # load_json_rows returns empty list (no rows in DB)
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


def _make_xlsx_bytes(headers: list[str], rows: list[list]) -> bytes:
    """Create minimal xlsx in-memory with given headers and data rows."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# Export Template Tests (4表)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_template_g6_5():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/export-template?sheet=G6-5"
        )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_export_template_g6_6():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/export-template?sheet=G6-6"
        )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_export_template_g6_9():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/export-template?sheet=G6-9"
        )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_export_template_g6_10():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/export-template?sheet=G6-10"
        )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats" in resp.headers["content-type"]


# ═══════════════════════════════════════════════════════════════════════════════
# Export Data Test (empty workbook)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_data_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/export-data?sheet=G6-5"
        )
    assert resp.status_code == 200
    assert "application/vnd.openxmlformats" in resp.headers["content-type"]


# ═══════════════════════════════════════════════════════════════════════════════
# Import Data Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_import_data_g6_9():
    """Import valid xlsx with G6-9 data rows → 200, imported_count > 0."""
    xlsx_bytes = _make_xlsx_bytes(
        ["证券名称", "证券代码", "面值", "数量(盘点)", "数量(账面)"],
        [
            ["国开债2024A", "101001", 1000000, 100, 100],
            ["农发债2024B", "101002", 500000, 50, 50],
        ],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/import-data?sheet=G6-9",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200
    data = resp.json()
    # ResponseWrapperMiddleware wraps as {code, message, data}
    payload = data.get("data", data)
    assert payload["imported_count"] > 0


@pytest.mark.asyncio
async def test_import_data_invalid_format():
    """Import non-xlsx (txt file) → 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/import-data?sheet=G6-9",
            files={"file": ("test.txt", b"invalid content", "text/plain")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_data_invalid_sheet():
    """Import with unsupported sheet code → 400."""
    xlsx_bytes = _make_xlsx_bytes(["col1"], [["val"]])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/import-data?sheet=G6-99",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# AI Endpoint Tests (4 sections + invalid)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ai_fair_value_conclusion(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "公允价值测试审计结论初稿"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/ai/fair-value-conclusion",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 200
    payload = resp.json().get("data", resp.json())
    assert payload["content"] == "公允价值测试审计结论初稿"


@pytest.mark.asyncio
async def test_ai_interest_conclusion(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "利息测算审计结论初稿"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/ai/interest-conclusion",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 200
    payload = resp.json().get("data", resp.json())
    assert payload["content"] == "利息测算审计结论初稿"


@pytest.mark.asyncio
async def test_ai_business_model_conclusion(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "业务模式分析综合判断初稿"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/ai/business-model-conclusion",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 200
    payload = resp.json().get("data", resp.json())
    assert payload["content"] == "业务模式分析综合判断初稿"


@pytest.mark.asyncio
async def test_ai_sppi_conclusion(monkeypatch):
    async def _fake_chat(**_kwargs):
        return "SPPI测试综合结论初稿"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g6_other_bond_investment_sppi_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/ai/sppi-conclusion",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 200
    payload = resp.json().get("data", resp.json())
    assert payload["content"] == "SPPI测试综合结论初稿"


@pytest.mark.asyncio
async def test_ai_invalid_section():
    """Invalid section name → 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g6-sppi/ai/invalid-section",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 400
