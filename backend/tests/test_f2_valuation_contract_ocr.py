"""Tests for F2-47 impairment contract OCR endpoint.

spec attachment-evidence-intake 起识别前先建附件并关联底稿：用例跑在 SQLite 世界（真实底稿行、附件存储在临时目录），
只挂本路由、不挂统一门；识别引擎与大模型在路由模块下一层打桩。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.wp_render_strategies._f2_valuation_contract_ocr import router as f2_val_router
from tests.attachment_evidence_intake._helpers import ocr_world, pdf, unwrap


@pytest.fixture
def llm_impairment_json():
    return json.dumps({
        "itemName": "原材料甲",
        "qty": 100,
        "unitCost": 5.5,
        "sellingPrice": 4.2,
        "completionCost": 0,
        "sellingExpense": 0.3,
        "tax": 0.1,
    }, ensure_ascii=False)


@pytest.mark.asyncio
async def test_f2_val_impairment_ocr_returns_fields(monkeypatch, tmp_path, llm_impairment_json):
    async with ocr_world(monkeypatch, tmp_path, f2_val_router, wp_code="F2-47") as w:
        with (
            patch("app.routers.wp_render_strategies._f2_valuation_contract_ocr.UnifiedOCRService") as MockOCR,
            patch("app.routers.wp_render_strategies._f2_valuation_contract_ocr.chat_completion", new_callable=AsyncMock) as mock_llm,
        ):
            MockOCR.return_value.recognize = AsyncMock(return_value={"text": "存货 原材料甲 数量100 单价5.5"})
            mock_llm.return_value = llm_impairment_json
            response = await w.client.post(f"/api/workpapers/{w.wp.id}/f2-val/contract-ocr", files=pdf("nrv.pdf"))
    assert response.status_code == 200, response.text
    data = unwrap(response.json())
    assert "attachment_id" in data
    fields = data["extracted_fields"]
    assert fields.get("itemName") == "原材料甲"
    assert fields.get("qty") == 100
    assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_f2_val_impairment_ocr_rejects_invalid_suffix(monkeypatch, tmp_path):
    async with ocr_world(monkeypatch, tmp_path, f2_val_router, wp_code="F2-47") as w:
        response = await w.client.post(
            f"/api/workpapers/{w.wp.id}/f2-val/contract-ocr", files={"file": ("bad.txt", b"text", "text/plain")},
        )
    assert response.status_code == 400
    assert "不支持的文件类型" in json.dumps(response.json(), ensure_ascii=False)
