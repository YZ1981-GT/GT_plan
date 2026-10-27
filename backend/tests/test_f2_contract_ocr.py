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
from app.routers._wp_gate import dedicated_wp_gate
from app.services import workpaper_side_storage

# 底稿 ID 必须是合法 UUID：非 UUID 直接 400（spec attachment-security-baseline 需求 1.6）
_WP_ID = "7d4c0a1e-3b2f-4c5d-9e8f-0a1b2c3d4ef2"


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps(monkeypatch, tmp_path):
    async def _override_db():
        yield AsyncMock()

    async def _skip_wp_gate():
        # 本文件测识别与字段提取；可见性门另有 procedure_delegation_visibility 套件覆盖
        return None

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[dedicated_wp_gate] = _skip_wp_gate
    monkeypatch.setattr(workpaper_side_storage, "SIDE_STORAGE_ROOT", tmp_path / "workpapers")
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
                f"/api/workpapers/{_WP_ID}/f2/contract-ocr",
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
            f"/api/workpapers/{_WP_ID}/f2/contract-ocr",
            files={"file": ("bad.txt", io.BytesIO(b"text"), "text/plain")},
        )
    assert response.status_code == 400
    assert "不支持的文件类型" in json.dumps(response.json(), ensure_ascii=False)
