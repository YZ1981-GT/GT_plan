"""Tests for D4 contract OCR endpoint.

POST /api/workpapers/{wp_id}/d4/contract-ocr
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole


# ─── Fixtures ─────────────────────────────────────────────────────────────────

class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    """Override auth and DB dependencies for all tests."""
    async def _override_db():
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def sample_pdf_content():
    """Minimal PDF-like binary content for upload."""
    return b"%PDF-1.4 fake content for testing"


@pytest.fixture
def ocr_result():
    """Sample OCR result."""
    return {
        "text": "合同编号：HT-2025-001\n甲方：测试科技有限公司\n签订日期：2025年3月15日\n合同金额：人民币伍拾万元整（500000.00元）",
        "engine": "paddle",
        "regions": [],
    }


@pytest.fixture
def llm_extracted_json():
    """Sample LLM extraction result."""
    return json.dumps({
        "contractNo": "HT-2025-001",
        "counterparty": "测试科技有限公司",
        "signDate": "2025-03-15",
        "serviceContent": "软件开发服务",
        "contractAmount": 500000,
        "deliveryTime": "2025-12-31",
        "deliveryMethod": "线上交付",
        "settlementMethod": "分期付款",
        "settlementTime": "验收后30天",
        "warrantyClause": "一年免费维护",
        "returnClause": "",
        "breachClause": "违约金10%",
        "specialTerms": "",
        "isSigned": "Y",
        "isSealed": "Y",
        "recognitionMethod": "时段法",
        "acceptanceClause": "双方验收确认",
        "recognitionTime": "按进度确认",
        "controlTransferDoc": "验收报告",
        "specialTransaction": "",
    }, ensure_ascii=False)


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contract_ocr_returns_200_with_valid_upload(
    sample_pdf_content, ocr_result, llm_extracted_json
):
    """Test endpoint returns 200 with valid file upload (mock OCR + mock LLM)."""
    with (
        patch("app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._d4_contract_ocr.chat_completion") as mock_llm,
    ):
        ocr_instance = MockOCR.return_value
        ocr_instance.recognize = AsyncMock(return_value=ocr_result)
        mock_llm.return_value = llm_extracted_json

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d4/contract-ocr",
                files={"file": ("contract.pdf", io.BytesIO(sample_pdf_content), "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        # ResponseWrapperMiddleware wraps in {code, message, data}
        if "data" in data and isinstance(data["data"], dict) and "attachment_id" in data["data"]:
            data = data["data"]

        assert "attachment_id" in data
        assert "ocr_text" in data
        assert "extracted_fields" in data
        assert "confidence" in data
        assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_contract_ocr_returns_correct_schema_keys(
    sample_pdf_content, ocr_result, llm_extracted_json
):
    """Test endpoint returns extracted_fields with correct 20 schema keys."""
    with (
        patch("app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._d4_contract_ocr.chat_completion") as mock_llm,
    ):
        ocr_instance = MockOCR.return_value
        ocr_instance.recognize = AsyncMock(return_value=ocr_result)
        mock_llm.return_value = llm_extracted_json

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d4/contract-ocr",
                files={"file": ("contract.pdf", io.BytesIO(sample_pdf_content), "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        if "data" in data and isinstance(data["data"], dict) and "extracted_fields" in data["data"]:
            data = data["data"]

        fields = data["extracted_fields"]
        expected_keys = {
            "contractNo", "counterparty", "signDate", "serviceContent",
            "contractAmount", "deliveryTime", "deliveryMethod", "settlementMethod",
            "settlementTime", "warrantyClause", "returnClause", "breachClause",
            "specialTerms", "isSigned", "isSealed", "recognitionMethod",
            "acceptanceClause", "recognitionTime", "controlTransferDoc", "specialTransaction",
        }
        assert set(fields.keys()) == expected_keys


@pytest.mark.asyncio
async def test_ocr_failure_returns_empty_fields(sample_pdf_content):
    """Test OCR failure gracefully returns empty fields."""
    with (
        patch("app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService") as MockOCR,
    ):
        ocr_instance = MockOCR.return_value
        ocr_instance.recognize = AsyncMock(side_effect=Exception("OCR service unavailable"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d4/contract-ocr",
                files={"file": ("contract.png", io.BytesIO(sample_pdf_content), "image/png")},
            )

        assert response.status_code == 200
        data = response.json()
        if "data" in data and isinstance(data["data"], dict) and "extracted_fields" in data["data"]:
            data = data["data"]

        assert data["ocr_text"] == ""
        assert data["confidence"] == 0
        # All fields should be empty/zero
        fields = data["extracted_fields"]
        for key, val in fields.items():
            if key == "contractAmount":
                assert val == 0
            else:
                assert val == ""


@pytest.mark.asyncio
async def test_llm_failure_returns_empty_fields_with_ocr_text(
    sample_pdf_content, ocr_result
):
    """Test LLM failure gracefully returns empty fields but preserves ocr_text."""
    with (
        patch("app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._d4_contract_ocr.chat_completion") as mock_llm,
    ):
        ocr_instance = MockOCR.return_value
        ocr_instance.recognize = AsyncMock(return_value=ocr_result)
        mock_llm.side_effect = Exception("LLM service timeout")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/d4/contract-ocr",
                files={"file": ("contract.jpg", io.BytesIO(sample_pdf_content), "image/jpeg")},
            )

        assert response.status_code == 200
        data = response.json()
        if "data" in data and isinstance(data["data"], dict) and "extracted_fields" in data["data"]:
            data = data["data"]

        # OCR text should be preserved
        assert data["ocr_text"] != ""
        assert "合同编号" in data["ocr_text"]
        # But fields should be empty due to LLM failure
        assert data["confidence"] == 0
        fields = data["extracted_fields"]
        for key, val in fields.items():
            if key == "contractAmount":
                assert val == 0
            else:
                assert val == ""


@pytest.mark.asyncio
async def test_invalid_file_type_returns_400():
    """Test invalid file extension returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/d4/contract-ocr",
            files={"file": ("contract.docx", io.BytesIO(b"fake"), "application/vnd.openxmlformats")},
        )

    # Should reject unsupported file type
    assert response.status_code in (400, 422)
