"""Tests for F2 purchase contract OCR endpoint."""
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


@pytest.fixture
def llm_purchase_json():
    return json.dumps({
        "purchaseOrderNo": "PO-2025-001",
        "orderDate": "2025-03-15",
        "amount": 88000,
        "supplier": "测试供应商有限公司",
        "invoiceNo": "INV-001",
        "itemName": "原材料A",
    }, ensure_ascii=False)


@pytest.mark.asyncio
async def test_f2_contract_ocr_returns_fields(llm_purchase_json):
    with (
        patch("app.routers.wp_render_strategies._f2_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._f2_contract_ocr.chat_completion", new_callable=AsyncMock) as mock_llm,
    ):
        MockOCR.return_value.recognize = AsyncMock(return_value={"text": "采购订单 PO-2025-001 金额88000"})
        mock_llm.return_value = llm_purchase_json
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/workpapers/test-wp-id/f2/contract-ocr",
                files={"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        assert "attachment_id" in data
        assert "extracted_fields" in data
        assert data["extracted_fields"].get("supplier") == "测试供应商有限公司"
        assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_f2_contract_ocr_rejects_invalid_suffix():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/workpapers/test-wp-id/f2/contract-ocr",
            files={"file": ("bad.txt", io.BytesIO(b"text"), "text/plain")},
        )
    assert response.status_code == 400
