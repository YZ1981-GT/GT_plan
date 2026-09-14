"""G7 长期股权投资(main组) — API 集成测试（render + 导入导出 + AI）.

Validates: Requirements 1.1, 6.4, 6.5

测试清单:
1. render-config 返回正确 componentType='g7-long-term-equity-main' + 7 sheets
2. export-template G7-2 → 200 + xlsx content-type
3. export-template G7-3 → 200 + xlsx content-type
4. export-data G7-2 → 200 (multi-sheet xlsx)
5. export-data G7-3 → 200
6. import-data G7-2 → 200 + imported_count
7. import-data G7-3 → 200 + imported_count
8. AI adjudication-analysis → 200
9. AI disclosure-text → 200
10. AI invalid-section → 400
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._g7_long_term_equity_main import (
    G7_MAIN_SHEETS,
)
from app.routers.wp_render_strategies._g7_long_term_equity_main_import_export import (
    _SUPPORTED_SHEETS,
    _parse_g7_2_import,
    _validate_g7_2_rows,
)


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


def _make_xlsx_g7_2() -> bytes:
    """Create a minimal valid G7-2 three-business-section workbook."""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    cost = wb.create_sheet("成本法")
    cost.append(["G7-2 长期股权投资明细表 — 成本法"])
    cost.append([
        "记录ID", "序号", "被投资单位名称", "初始投资成本", "投资比例",
        "未审期初金额", "未审增加金额", "未审减少金额", "期初AJE", "本期增加AJE",
    ])
    cost.append(["cost-1", 1, "测试子公司A", 1_000_000, 0.51, 1_000_000, 500_000, 0, 0, 0])

    equity = wb.create_sheet("权益法")
    equity.append(["G7-2 长期股权投资明细表 — 权益法"])
    equity.append([
        "记录ID", "序号", "被投资单位名称", "初始投资成本", "投资比例",
        "投资关系", "未审期初金额", "投资成本增加", "损益调整",
    ])
    equity.append(["equity-1", 1, "测试联营企业", 800_000, 0.30, "associate", 800_000, 0, 60_000])

    impairment = wb.create_sheet("减值准备")
    impairment.append(["G7-2 长期股权投资明细表 — 减值准备"])
    impairment.append([
        "记录ID", "序号", "被投资单位名称", "来源记录ID", "投资关系",
        "未审期初", "未审增加", "未审减少",
    ])
    impairment.append(["impair-1", 1, "测试子公司A", "cost-1", "subsidiary", 0, 20_000, 0])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _make_xlsx_g7_3() -> bytes:
    """Create a minimal valid G7-3 xlsx for import testing."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "G7-3"
    # Title row
    ws.append(["G7-3 调整分录汇总"])
    # Header row (row 2)
    ws.append(["调整事项说明", "类别（报表调整/账项调整/其他）", "报表项目", "科目名称",
               "附注项目", "……", "借方调整金额", "贷方调整金额", "索引", "备注"])
    # Data row
    ws.append(["调增长期股权投资", "账项调整", "长期股权投资", "长期股权投资",
               "", "", 100000, 0, "G7-3", "权益法调整"])
    ws.append(["调增长期股权投资", "账项调整", "投资收益", "投资收益",
               "", "", 0, 100000, "G7-3", "对应科目"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def test_parse_original_g7_2_coordinates():
    """原始合并表头模板按固定业务区坐标导入，不依赖系统三sheet格式。"""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "明细表G7-2"
    # 成本法第1行：B/F/H/K/M/O/R/V/W/X/Y/Z/AA
    for col, value in {
        1: 1, 2: "原表子公司", 6: 100, 8: 0.6, 11: 3,
        12: 0.6, 13: 100, 14: 0.1, 15: 20, 17: 0.05, 18: 5,
        22: 2, 23: -1, 24: 4, 25: 1, 26: 0, 27: 2,
    }.items():
        ws.cell(16, col, value)
    # 权益法合营第1行：B:H、J:M、Q:R、V:W、X:AE、AF:AM
    for col, value in {
        1: 1, 2: "原表合营企业", 3: 80, 4: 0.3, 7: 0.3, 8: 80,
        10: 10, 11: 6, 12: 2, 13: 1, 17: 3, 18: 4,
        22: 1, 23: 0, 24: 2, 25: 1, 32: 0, 33: 1,
    }.items():
        ws.cell(33, col, value)
    # 两项对应的减值明细。
    ws.cell(53, 7, 5)
    ws.cell(53, 8, 2)
    ws.cell(66, 7, 1)

    buf = io.BytesIO()
    wb.save(buf)
    rows, errors = _parse_g7_2_import(buf.getvalue())

    assert errors == []
    assert [row["section"] for row in rows] == [
        "cost", "equity", "impairment", "impairment",
    ]
    assert rows[0]["investeeName"] == "原表子公司"
    assert rows[0]["openingAmount"] == 100
    assert rows[1]["relationship"] == "joint_venture"
    assert rows[2]["sourceId"] == rows[0]["id"]


def test_validate_g7_2_rejects_overridden_formula():
    rows = [{
        "id": "cost-1",
        "section": "cost",
        "investeeName": "子公司A",
        "openingAmount": 100,
        "increaseAmount": 20,
        "decreaseAmount": 5,
        "closingAmount": 999,
        "openingAje": 0,
        "openingRje": 0,
        "ajeIncrease": 0,
        "rjeIncrease": 0,
        "ajeDecrease": 0,
        "rjeDecrease": 0,
        "auditedOpeningAmount": 100,
        "auditedIncreaseAmount": 20,
        "auditedDecreaseAmount": 5,
        "auditedClosingAmount": 115,
    }]

    errors = _validate_g7_2_rows(rows)

    assert len(errors) == 1
    assert errors[0]["field"] == "closingAmount"
    assert errors[0]["expected"] == 115


# ═══════════════════════════════════════════════════════════════════════════════
# 1. render-config: componentType + 7 sheets
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_g7_main_render_dispatch_registered():
    """render-config returns correct componentType and 7 sheets config."""
    assert "g7-long-term-equity-main" in RENDERER_DISPATCH
    fn = RENDERER_DISPATCH["g7-long-term-equity-main"]
    assert callable(fn)
    assert len(G7_MAIN_SHEETS) == 7
    # Verify component_type in sheets
    for sheet in G7_MAIN_SHEETS:
        assert "sheetName" in sheet
        assert "code" in sheet


@pytest.mark.asyncio
async def test_g7_main_supported_sheets():
    """Verify _SUPPORTED_SHEETS covers G7-2 and G7-3."""
    assert _SUPPORTED_SHEETS == {"G7-2", "G7-3"}


# ═══════════════════════════════════════════════════════════════════════════════
# 2-3. export-template: G7-2 / G7-3
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G7-2", "G7-3"])
async def test_g7_main_export_template(sheet: str):
    """POST export-template → 200 + xlsx content-type."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/g7-main/export-template?sheet={sheet}")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 4-5. export-data: G7-2 / G7-3
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("sheet", ["G7-2", "G7-3"])
async def test_g7_main_export_data(sheet: str, override_deps):
    """POST export-data → 200 (multi-sheet xlsx for G7-2, single-sheet for G7-3)."""
    # Mock load_json_rows to return empty list (no data)
    mock_db = override_deps
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/workpapers/test-wp/g7-main/export-data?sheet={sheet}")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. import-data: G7-2 (multipart xlsx)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_g7_main_import_data_g7_2(override_deps):
    """POST import-data G7-2 multipart → 200 + imported_count."""
    mock_db = override_deps
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

    xlsx_bytes = _make_xlsx_g7_2()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-main/import-data?sheet=G7-2",
            files={"file": ("G7-2_test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200
    data = resp.json()
    # ResponseWrapperMiddleware wraps in {code, message, data}
    payload = data.get("data", data)
    assert payload.get("imported_count", 0) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 7. import-data: G7-3 (multipart xlsx)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_g7_main_import_data_g7_3(override_deps):
    """POST import-data G7-3 multipart → 200 + imported_count."""
    mock_db = override_deps
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

    xlsx_bytes = _make_xlsx_g7_3()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-main/import-data?sheet=G7-3",
            files={"file": ("G7-3_test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200
    data = resp.json()
    payload = data.get("data", data)
    assert payload.get("imported_count", 0) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 8-9. AI: adjudication-analysis / disclosure-text
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["adjudication-analysis", "disclosure-text"])
async def test_g7_main_ai_section(section: str, monkeypatch, override_deps):
    """POST AI section → 200."""
    mock_db = override_deps
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

    async def _fake_chat(**_kwargs):
        return "AI生成的审计分析内容"

    monkeypatch.setattr(
        "app.routers.wp_render_strategies._g7_long_term_equity_main_ai.chat_completion",
        _fake_chat,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/workpapers/test-wp/g7-main/ai/{section}",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 200, f"section={section} failed: {resp.text}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. AI: invalid/unsupported section → 400
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_g7_main_ai_invalid_section(override_deps):
    """POST AI invalid-section → 400."""
    mock_db = override_deps
    mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/workpapers/test-wp/g7-main/ai/invalid-section",
            json={"existingContent": "", "relatedContext": {}},
        )
    assert resp.status_code == 400
