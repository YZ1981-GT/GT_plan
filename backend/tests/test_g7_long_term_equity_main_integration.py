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
    """Create a minimal valid G7-2 multi-sheet xlsx for import testing."""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    # Segment 1: 基础信息
    ws1 = wb.create_sheet("基础信息")
    ws1.append(["G7-2 明细表 — 基础信息"])
    ws1.append(["被投资单位名称", "控制类型", "持股比例(%)", "投票权比例(%)",
                "行业", "注册地", "主营业务", "是否关联方"])
    ws1.append(["测试子公司A", "子公司", "51.00", "51.00", "制造业", "上海", "电子产品", "否"])

    # Segment 2: 期初余额
    ws2 = wb.create_sheet("期初余额")
    ws2.append(["G7-2 明细表 — 期初余额"])
    ws2.append(["期初投资成本", "期初权益法调整", "期初减值准备", "期初账面价值",
                "期初审定成本", "期初审定权益法", "期初审定减值",
                "期初审定净值", "期初余额备注", "序号"])
    ws2.append([1000000, 0, 0, 1000000, 1000000, 0, 0, 1000000, "", 1])

    # Segment 3: 本期变动
    ws3 = wb.create_sheet("本期变动")
    ws3.append(["G7-2 明细表 — 本期变动"])
    ws3.append(["本期增加(新增投资)", "本期增加(权益法)", "本期减少(处置)",
                "本期减少(权益法调整)", "本期减值计提", "本期减值转回",
                "被投资单位净利润", "持股比例调整", "其他综合收益",
                "其他权益变动", "利润分配", "变动备注"])
    ws3.append([500000, 0, 0, 0, 0, 0, 200000, 0, 0, 0, 50000, ""])

    # Segment 4: 期末+减值
    ws4 = wb.create_sheet("期末+减值")
    ws4.append(["G7-2 明细表 — 期末+减值"])
    ws4.append(["期末投资成本", "期末权益法调整", "期末小计",
                "期末减值准备", "期末账面价值", "审定调整",
                "审定数", "可收回金额", "减值测试结论",
                "发函情况", "索引", "期末备注"])
    ws4.append([1500000, 0, 1500000, 0, 1500000, 0, 1500000, 1800000, "无减值", "已回函", "G7-2-1", ""])

    # Segment 5: 权益法详情
    ws5 = wb.create_sheet("权益法详情")
    ws5.append(["G7-2 明细表 — 权益法详情"])
    ws5.append(["被投资方净资产", "享有份额", "商誉",
                "内部交易抵销", "未确认损失", "权益法投资收益",
                "本期OCI", "股利收入", "计量方法确认",
                "处置损益", "权益法备注", "权益法序号"])
    ws5.append([3000000, 1530000, 0, 0, 0, 0, 0, 50000, "成本法", 0, "", 1])

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
    ws.append(["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称",
               "借方金额", "贷方金额", "编制人", "备注"])
    # Data row
    ws.append([1, "AJE", "2025-12-31", "调增长期股权投资",
               "1511", "长期股权投资", 100000, 0, "张三", "权益法调整"])
    ws.append([2, "AJE", "2025-12-31", "调增长期股权投资",
               "6111", "投资收益", 0, 100000, "张三", "对应科目"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


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
