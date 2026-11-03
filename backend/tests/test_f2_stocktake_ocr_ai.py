"""Tests for F2 stocktake OCR and AI endpoints.

识别端点自 spec attachment-evidence-intake 起先建附件并关联底稿：识别用例跑在 SQLite 世界（真实底稿行、附件存储在
临时目录），只挂本路由、不挂统一门；生成用例仍挂完整应用。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers._wp_gate import dedicated_wp_gate
from app.routers.wp_render_strategies._f2_stocktake_contract_ocr import router as f2_st_router
from tests.attachment_evidence_intake._helpers import ocr_world, pdf, unwrap


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    async def _override_db():
        yield AsyncMock()

    async def _skip_wp_gate():
        # 本文件测识别与生成；可见性门另有 procedure_delegation_visibility 套件覆盖
        return None

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[dedicated_wp_gate] = _skip_wp_gate
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_f2_st_contract_ocr_f2_25(monkeypatch, tmp_path):
    llm_json = json.dumps({
        "itemName": "原材料A",
        "spec": "10mm",
        "unit": "件",
        "bookQty": 100,
        "sampleQty": 98,
        "varianceReason": "计量误差",
    }, ensure_ascii=False)
    async with ocr_world(monkeypatch, tmp_path, f2_st_router, wp_code="F2-25") as w:
        with (
            patch("app.routers.wp_render_strategies._f2_stocktake_contract_ocr.UnifiedOCRService") as MockOCR,
            patch("app.routers.wp_render_strategies._f2_stocktake_contract_ocr.chat_completion", new_callable=AsyncMock) as mock_llm,
        ):
            MockOCR.return_value.recognize = AsyncMock(return_value={"text": "抽盘记录 原材料A 账面100 实盘98"})
            mock_llm.return_value = llm_json
            response = await w.client.post(f"/api/workpapers/{w.wp.id}/f2-st/contract-ocr?sheet=F2-25", files=pdf("count.pdf"))
    assert response.status_code == 200, response.text
    data = unwrap(response.json())
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
async def test_f2_st_ai_generate_questionnaire_field():
    with patch(
        "app.routers.wp_render_strategies._f2_stocktake_ai.chat_completion",
        new_callable=AsyncMock,
    ) as mock_llm:
        mock_llm.return_value = "本项目未聘请外部专家；盘点以项目组自行观察与抽盘为主。"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp/f2-st/ai-generate",
                json={
                    "section": "stocktake-questionnaire-field",
                    "existingContent": "",
                    "relatedContext": {
                        "questionId": "q3",
                        "questionNo": "3",
                        "questionLabel": "是否有专家参与？如何安排？",
                        "locations": "主仓/原材料",
                    },
                },
            )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        assert "专家" in data["content"]
        msgs = mock_llm.await_args.kwargs["messages"]
        assert "当前题目" in msgs[-1]["content"]
        assert "是否有专家参与" in msgs[-1]["content"]


@pytest.mark.asyncio
async def test_f2_st_ocr_rejects_invalid_sheet(monkeypatch, tmp_path):
    async with ocr_world(monkeypatch, tmp_path, f2_st_router, wp_code="F2-25") as w:
        response = await w.client.post(f"/api/workpapers/{w.wp.id}/f2-st/contract-ocr?sheet=F2-22", files=pdf("x.pdf"))
    assert response.status_code == 400
    assert "不支持的 sheet" in json.dumps(response.json(), ensure_ascii=False)
