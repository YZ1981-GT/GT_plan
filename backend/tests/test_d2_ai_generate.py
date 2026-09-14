"""Tests for D2 accounts receivable AI generate endpoint."""
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
async def test_d2_ai_generate_adj_note():
    with patch(
        "app.routers.wp_render_strategies._d2_ai_generate.chat_completion",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = "应收账款期末余额较期初变动合理，已执行函证及账龄分析。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d2/ai-generate",
                json={
                    "section": "adj-note",
                    "existingContent": "",
                    "relatedContext": {"grossTotal": 5000000},
                },
            )
        assert response.status_code == 200
        data = response.json()
        payload = data.get("data", data)
        assert "content" in payload
        assert len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_d2_ai_generate_writeoff_analysis():
    with patch(
        "app.routers.wp_render_strategies._d2_ai_generate.chat_completion",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = "转回金额与期后回款匹配，核销已履行审批程序。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d2/ai-generate",
                json={
                    "section": "writeoff-analysis",
                    "existingContent": "",
                    "relatedContext": {
                        "reversalTotal": 100000,
                        "writeoffTotal": 50000,
                    },
                },
            )
        assert response.status_code == 200
        payload = response.json().get("data", response.json())
        assert "转回" in payload["content"] or len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_d2_ai_generate_rejects_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/d2/ai-generate",
            json={"section": "unknown-section", "existingContent": ""},
        )
    assert response.status_code == 400
