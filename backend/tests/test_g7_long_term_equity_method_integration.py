"""G7 长期股权投资(权益法组) — API 集成测试（导入导出 + AI）.

Validates: Requirements 7.3, 7.4

测试清单:
1. G7-4 export-template → source-aligned single data sheet + validations
2. G7-13/G7-14/G7-16 export-template → 200 + multi-sheet xlsx (2 sheets)
3. G7-5/G7-15/G7-17 export-template → 200 + single-sheet xlsx
4. AI invalid section → 400
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    """Mock DB and auth dependencies for all tests."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))
    mock_db.flush = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. G7-4原底稿单sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_export_g7_4_source_aligned_template():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-equity-method/export-template?sheet=G7-4"
        )

    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert "G7-4" in wb.sheetnames
    ws = wb["G7-4"]
    headers = [cell.value for cell in ws[2]]
    assert headers[:5] == [
        "投资关系",
        "公司名称",
        "级次（国企适用）",
        "企业类型（国企适用）",
        "是否为本期新纳入合并范围的子公司（国企适用）",
    ]
    validations = {
        str(validation.sqref): validation.formula1
        for validation in ws.data_validations.dataValidation
    }
    assert validations["D3:D502"] == '"1,2,3,4,5"'
    assert validations["E3:E502"] == '"是,否"'
    wb.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 宽表分sheet导出：G7-13/G7-14/G7-16 → multi-sheet (2 data sheets)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sheet_code", ["G7-13", "G7-14", "G7-16"])
async def test_export_template_multi_sheet(sheet_code: str):
    """POST export-template for multi-sheet tables → 200 + xlsx with ≥2 worksheets.

    G7-13(2区段Tab) / G7-14(2区段Tab) / G7-16(2区段Tab)
    导出模板时按区段分sheet，每个表至少2个data worksheets。

    **Validates: Requirements 7.3**
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/workpapers/test-wp/g7-equity-method/export-template?sheet={sheet_code}"
        )

    assert resp.status_code == 200, f"{sheet_code} failed: {resp.text}"
    assert "spreadsheetml" in resp.headers.get("content-type", "")

    # Parse xlsx and verify multi-sheet structure
    wb = load_workbook(io.BytesIO(resp.content), read_only=True)
    sheet_names = wb.sheetnames
    wb.close()

    # 宽表导出：至少2个data sheet + 可能有编制说明sheet
    # 所以总sheet数 ≥ 2
    assert len(sheet_names) >= 2, (
        f"{sheet_code} expected ≥2 sheets, got {len(sheet_names)}: {sheet_names}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 单sheet导出：G7-5/G7-15/G7-17 → single-sheet xlsx
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sheet_code", ["G7-5", "G7-15", "G7-17"])
async def test_export_template_single_sheet(sheet_code: str):
    """POST export-template for single-sheet tables → 200 + xlsx with 1 data worksheet.

    G7-5(10列) / G7-15(14列) / G7-17(9列) 不需要区段拆分，导出为单个data sheet。

    **Validates: Requirements 7.3**
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/workpapers/test-wp/g7-equity-method/export-template?sheet={sheet_code}"
        )

    assert resp.status_code == 200, f"{sheet_code} failed: {resp.text}"
    assert "spreadsheetml" in resp.headers.get("content-type", "")

    # Parse xlsx — single data sheet (may have guidance sheet)
    wb = load_workbook(io.BytesIO(resp.content), read_only=True)
    sheet_names = wb.sheetnames
    wb.close()

    # 单sheet表：主数据sheet名=sheet_code，可能有编制说明
    # 但data sheets只有1个（主sheet）
    # 总数不超过2（主sheet + 可选编制说明）
    assert len(sheet_names) <= 2, (
        f"{sheet_code} expected ≤2 sheets (data + guidance), got {len(sheet_names)}: {sheet_names}"
    )
    # 确认不是多区段拆分格式（不含"+"字样的区段名）
    segment_like = [s for s in sheet_names if "+" in s or "区段" in s]
    assert len(segment_like) == 0, (
        f"{sheet_code} should not have segment-split sheets: {segment_like}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AI invalid section → 400
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ai_invalid_section_returns_400():
    """POST AI with invalid section → 400.

    **Validates: Requirements 7.4**
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-equity-method/ai/invalid-section",
            json={"existingContent": "", "relatedContext": {}},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ai_unsupported_section_error_message():
    """POST AI with unsupported section → 400 + descriptive error message."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-equity-method/ai/nonexistent-section",
            json={"existingContent": "", "relatedContext": {}},
        )

    assert resp.status_code == 400
    body = resp.json()
    # ResponseWrapperMiddleware may wrap; check detail or message
    detail = body.get("detail", body.get("message", ""))
    assert "不支持" in detail or "nonexistent" in detail.lower() or "section" in detail.lower()


@pytest.mark.asyncio
async def test_export_template_invalid_sheet_returns_400():
    """POST export-template with invalid sheet code → 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-equity-method/export-template?sheet=INVALID"
        )

    assert resp.status_code == 400
