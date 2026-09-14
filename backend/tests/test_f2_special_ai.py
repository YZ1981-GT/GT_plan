"""Tests for F2 special group AI generate endpoint."""
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
async def test_f2_spe_ai_generate_price_analysis():
    with patch("app.routers.wp_render_strategies._f2_special_ai.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "原材料采购价格总体平稳，个别材料波动需关注。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2-spe/ai-generate",
                json={"section": "price-analysis", "existingContent": "", "relatedContext": {"abnormalCount": 2}},
            )
        assert response.status_code == 200
        payload = response.json().get("data", response.json())
        assert "content" in payload
        assert len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_f2_spe_ai_rejects_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/f2-spe/ai-generate",
            json={"section": "unknown-section", "existingContent": ""},
        )
    assert response.status_code == 400
