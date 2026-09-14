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
async def test_f2_ai_generate_f2_20_abnormal():
    with patch("app.routers.wp_render_strategies._f2_inventory_main_ai.chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "产品A材料成本上涨约30%，进一步分析见F2-61。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2/ai-generate",
                json={
                    "section": "f2-20-abnormal",
                    "existingContent": "",
                    "relatedContext": {"anomalyCount": 1},
                },
            )
        assert response.status_code == 200
        data = response.json()
        payload = data.get("data", data)
        assert "F2-61" in payload["content"] or len(payload["content"]) > 0


@pytest.mark.asyncio
async def test_f2_ai_generate_rejects_unknown_section():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/f2/ai-generate",
            json={"section": "unknown-section", "existingContent": ""},
        )
    assert response.status_code == 400


# ════════════════════════════════════════════════════════════════════
# 附注披露 section 的 AI 覆盖（spec f2-inventory-disclosure-template-alignment
# Task 13.1 / 13.5）：两个披露 Tab 的每个文本域都要能调 AI，故 11 个 section
# 必须既在 _SUPPORTED_SECTIONS 中，又有非空 prompt（缺 prompt 会退化成无指令生成）。
# ════════════════════════════════════════════════════════════════════

_DISCLOSURE_SECTIONS = [
    "listed-note-category",
    "listed-note-nrv",
    "listed-note-provision",
    "listed-note-borrow",
    "listed-note-amort",
    "listed-note-re",
    "soe-note-category",
    "soe-note-borrow",
    "soe-note-amort",
    "soe-note-land",
    "soe-note",
]


@pytest.mark.parametrize("section", _DISCLOSURE_SECTIONS)
def test_disclosure_section_supported_and_has_prompt(section: str):
    from app.routers.wp_render_strategies import _f2_inventory_main_ai as mod

    assert section in mod._SUPPORTED_SECTIONS, f"{section} 未登记到 _SUPPORTED_SECTIONS"
    prompt = mod._SECTION_PROMPTS.get(section)
    assert prompt, f"{section} 缺少 prompt（会退化为无指令生成）"
    assert len(prompt) >= 20, f"{section} 的 prompt 过短，缺少审计口径约束：{prompt!r}"


def test_disclosure_prompts_reference_source_template_semantics():
    """披露 prompt 必须带口径约束，避免自造披露内容（铁律：禁止自造披露内容）。"""
    from app.routers.wp_render_strategies import _f2_inventory_main_ai as mod

    # 借款费用资本化 / 合同履约成本摊销 / 土地使用权：各自的专有口径关键词
    assert "借款费用" in mod._SECTION_PROMPTS["listed-note-borrow"]
    assert "借款费用" in mod._SECTION_PROMPTS["soe-note-borrow"]
    assert "合同履约成本" in mod._SECTION_PROMPTS["listed-note-amort"]
    assert "合同履约成本" in mod._SECTION_PROMPTS["soe-note-amort"]
    assert "土地" in mod._SECTION_PROMPTS["soe-note-land"]


@pytest.mark.asyncio
@pytest.mark.parametrize("section", _DISCLOSURE_SECTIONS)
async def test_f2_ai_generate_accepts_disclosure_sections(section: str):
    with patch(
        "app.routers.wp_render_strategies._f2_inventory_main_ai.chat_completion",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = "本期不存在需披露的相关事项。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2/ai-generate",
                json={"section": section, "existingContent": "", "relatedContext": {}},
            )
        assert response.status_code == 200, f"{section} 被拒绝：{response.text}"
        payload = response.json().get("data", response.json())
        assert len(payload["content"]) > 0
