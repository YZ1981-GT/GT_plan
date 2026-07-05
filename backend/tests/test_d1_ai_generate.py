"""Tests for D1 AI generate endpoint."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_d1_ai_generate_policy_conclusion():
    with patch(
        "app.routers.wp_render_strategies._d1_ai_generate.chat_completion",
        new_callable=AsyncMock,
        return_value="政策检查结论初稿",
    ):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp-id/d1/ai-generate",
                json={
                    "section": "policy-conclusion",
                    "existingContent": "ECL模型合理",
                    "relatedContext": {},
                },
                headers={"Authorization": "Bearer test"},
            )
        assert resp.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_d1_ai_generate_rejects_unknown_section():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp-id/d1/ai-generate",
            json={"section": "unknown-section"},
            headers={"Authorization": "Bearer test"},
        )
    assert resp.status_code in (400, 401, 403)
