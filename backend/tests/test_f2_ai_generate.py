"""Tests for F2 inventory main AI generate endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_f2_ai_generate_adj_note():
    with patch("app.routers.wp_render_strategies._f2_inventory_main_ai.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "存货总体状况良好，已执行收发存核对。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2/ai-generate",
                json={"section": "adj-note", "existingContent": "", "relatedContext": {"netTotal": 1000000}},
            )
        assert response.status_code == 200
        data = response.json()
        payload = data.get("data", data)
        assert "content" in payload
        assert len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_f2_ai_generate_f2_18_note_a():
    with patch("app.routers.wp_render_strategies._f2_inventory_main_ai.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "原材料占比上升，库存商品占比下降，结构变动需结合产销进一步分析。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2/ai-generate",
                json={
                    "section": "f2-18-note-a",
                    "existingContent": "",
                    "relatedContext": {"abnormalCount": 1},
                },
            )
        assert response.status_code == 200
        data = response.json()
        payload = data.get("data", data)
        assert len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_f2_ai_generate_rejects_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/f2/ai-generate",
            json={"section": "unknown-section", "existingContent": ""},
        )
    assert response.status_code == 400
