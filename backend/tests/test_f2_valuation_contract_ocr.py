"""Tests for F2-47 impairment contract OCR endpoint."""
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
_WP_ID = "7d4c0a1e-3b2f-4c5d-9e8f-0a1b2c3d4e47"


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
async def test_f2_val_impairment_ocr_returns_fields(llm_impairment_json):
    with (
        patch("app.routers.wp_render_strategies._f2_valuation_contract_ocr.UnifiedOCRService") as MockOCR,
        patch("app.routers.wp_render_strategies._f2_valuation_contract_ocr.chat_completion", new_callable=AsyncMock) as mock_llm,
    ):
        MockOCR.return_value.recognize = AsyncMock(return_value={"text": "存货 原材料甲 数量100 单价5.5"})
        mock_llm.return_value = llm_impairment_json
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/workpapers/{_WP_ID}/f2-val/contract-ocr",
                files={"file": ("nrv.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            )
        assert response.status_code == 200
        data = response.json().get("data", response.json())
        assert "attachment_id" in data
        fields = data["extracted_fields"]
        assert fields.get("itemName") == "原材料甲"
        assert fields.get("qty") == 100
        assert data["confidence"] > 0


@pytest.mark.asyncio
async def test_f2_val_impairment_ocr_rejects_invalid_suffix():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/workpapers/{_WP_ID}/f2-val/contract-ocr",
            files={"file": ("bad.txt", io.BytesIO(b"text"), "text/plain")},
        )
    assert response.status_code == 400
    assert "不支持的文件类型" in json.dumps(response.json(), ensure_ascii=False)
