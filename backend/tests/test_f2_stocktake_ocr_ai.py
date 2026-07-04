"""Tests for F2 stocktake OCR and AI endpoints."""
from __future__ import annotations

import io
import json
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
async def test_f2_st_contract_ocr_f2_25():
    llm_json = json.dumps({
        "itemName": "原材料A",
        "spec": "10mm",
        "unit": "件",
        "bookQty": 100,
        "sampleQty": 98,
        "varianceReason": "计量误差",
    }, ensure_ascii=False)
    with (
        patch("app.routers.wp_render_strategies._f2_stocktake_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._f2_stocktake_contract_ocr.chat_completion", new_callable=AsyncMock) as mock_llm,
    ):
        MockOCR.return_value.recognize = AsyncMock(return_value={"text": "抽盘记录 原材料A 账面100 实盘98"})
        mock_llm.return_value = llm_json
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp/f2-st/contract-ocr?sheet=F2-25",
                files={"file": ("count.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        assert data["sheet"] == "F2-25"
        assert data["extracted_fields"].get("itemName") == "原材料A"
        assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_f2_st_ai_generate_plan():
    with patch(
        "app.routers.wp_render_strategies._f2_stocktake_ai.chat_completion",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = "监盘计划初稿：覆盖全部仓库，抽盘比例达到重要性水平。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp/f2-st/ai-generate",
                json={"section": "stocktake-plan", "existingContent": "", "relatedContext": {}},
            )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        assert "监盘计划" in data["content"]


@pytest.mark.asyncio
async def test_f2_st_ocr_rejects_invalid_sheet():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp/f2-st/contract-ocr?sheet=F2-22",
            files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        )
    assert response.status_code == 400
