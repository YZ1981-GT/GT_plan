"""Tests for D4 contract OCR endpoint.

POST /api/workpapers/{wp_id}/d4/contract-ocr

spec attachment-evidence-intake 起，识别前先经证据入口建附件并关联底稿（需求 2）：
用例跑在 SQLite 世界里（真实底稿行 + 附件存储在临时目录），只挂本路由、不挂统一门；
识别引擎与大模型在路由模块的下一层打桩。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.routers.wp_render_strategies._d4_contract_ocr import router as d4_router
from tests.attachment_evidence_intake._helpers import ocr_world, pdf, unwrap

_MOD = "app.routers.wp_render_strategies._d4_contract_ocr"
_EXPECTED_KEYS = {
    "contractNo", "counterparty", "signDate", "serviceContent",
    "contractAmount", "deliveryTime", "deliveryMethod", "settlementMethod",
    "settlementTime", "warrantyClause", "returnClause", "breachClause",
    "specialTerms", "isSigned", "isSealed", "recognitionMethod",
    "acceptanceClause", "recognitionTime", "controlTransferDoc", "specialTransaction",
}


@pytest.fixture
def ocr_result():
    return {
        "text": "合同编号：HT-2025-001\n甲方：测试科技有限公司\n签订日期：2025年3月15日\n合同金额：人民币伍拾万元整（500000.00元）",
        "engine": "paddle",
        "regions": [],
    }


@pytest.fixture
def llm_extracted_json():
    return json.dumps({
        "contractNo": "HT-2025-001", "counterparty": "测试科技有限公司", "signDate": "2025-03-15",
        "serviceContent": "软件开发服务", "contractAmount": 500000, "deliveryTime": "2025-12-31",
        "deliveryMethod": "线上交付", "settlementMethod": "分期付款", "settlementTime": "验收后30天",
        "warrantyClause": "一年免费维护", "returnClause": "", "breachClause": "违约金10%", "specialTerms": "",
        "isSigned": "Y", "isSealed": "Y", "recognitionMethod": "时段法", "acceptanceClause": "双方验收确认",
        "recognitionTime": "按进度确认", "controlTransferDoc": "验收报告", "specialTransaction": "",
    }, ensure_ascii=False)


async def _post(w, name: str, *, ocr=None, ocr_error=None, llm=None, llm_error=None):
    with (
        patch(f"{_MOD}.UnifiedOCRService") as mock_ocr,
        patch(f"{_MOD}.chat_completion") as mock_llm,
    ):
        mock_ocr.return_value.recognize = AsyncMock(return_value=ocr, side_effect=ocr_error)
        mock_llm.return_value = llm
        if llm_error is not None:
            mock_llm.side_effect = llm_error
        return await w.client.post(f"/api/workpapers/{w.wp.id}/d4/contract-ocr", files=pdf(name))


@pytest.mark.asyncio
async def test_contract_ocr_returns_200_and_keeps_evidence(monkeypatch, tmp_path, ocr_result, llm_extracted_json):
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        response = await _post(w, "contract.pdf", ocr=ocr_result, llm=llm_extracted_json)
        assert response.status_code == 200, response.text
        data = unwrap(response.json())
        assert {"attachment_id", "ocr_text", "extracted_fields", "confidence"} <= set(data)
        assert data["confidence"] > 0
        att = (await w.db.execute(sa.select(Attachment))).scalar_one()
        await w.db.refresh(att)
        assert data["attachment_id"] == str(att.id)  # 真实附件 id，不再是临时 id
        assert data["written_back"] is True
        assert att.ocr_text == ocr_result["text"]
        assert att.attachment_type == "contract"


@pytest.mark.asyncio
async def test_contract_ocr_returns_correct_schema_keys(monkeypatch, tmp_path, ocr_result, llm_extracted_json):
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        response = await _post(w, "contract.pdf", ocr=ocr_result, llm=llm_extracted_json)
    assert response.status_code == 200, response.text
    assert set(unwrap(response.json())["extracted_fields"].keys()) == _EXPECTED_KEYS


@pytest.mark.asyncio
async def test_ocr_failure_returns_empty_fields(monkeypatch, tmp_path):
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        response = await _post(w, "contract.png", ocr_error=Exception("OCR service unavailable"))
    assert response.status_code == 200, response.text
    data = unwrap(response.json())
    assert data["ocr_text"] == ""
    assert data["confidence"] == 0
    for key, val in data["extracted_fields"].items():
        assert val == (0 if key == "contractAmount" else "")


@pytest.mark.asyncio
async def test_llm_failure_returns_empty_fields_with_ocr_text(monkeypatch, tmp_path, ocr_result):
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        response = await _post(w, "contract.jpg", ocr=ocr_result, llm_error=Exception("LLM service timeout"))
    assert response.status_code == 200, response.text
    data = unwrap(response.json())
    assert "合同编号" in data["ocr_text"]
    assert data["confidence"] == 0
    for key, val in data["extracted_fields"].items():
        assert val == (0 if key == "contractAmount" else "")


@pytest.mark.asyncio
async def test_invalid_file_type_returns_400(monkeypatch, tmp_path):
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        response = await w.client.post(
            f"/api/workpapers/{w.wp.id}/d4/contract-ocr",
            files={"file": ("contract.docx", b"fake", "application/vnd.openxmlformats")},
        )
        assert response.status_code == 400
        assert "不支持的文件类型" in json.dumps(response.json(), ensure_ascii=False)
        assert (await w.db.execute(sa.select(sa.func.count()).select_from(Attachment))).scalar_one() == 0
