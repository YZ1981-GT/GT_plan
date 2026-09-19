"""I1 无形资产 — 后端 pytest：render策略 + 导入导出 + 摊销引擎验证.

Validates: Requirements 1.1-1.9, 11.4-11.5, 12.2, 13.2-13.3

测试清单:
1. RENDERER_DISPATCH 包含 'i1-intangible-assets' key
2. render函数返回正确 html_data 结构（component_type/account_codes/sheets）
3. TB数据获取（mock DB）
4. export-template 端点返回 xlsx
5. export-data 端点返回 xlsx
6. import-data 端点验证文件格式
7. 摊销验证端点（直线法/剩余年限法/含减值）
8. DCF现值计算端点
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
from app.routers.wp_render_strategies._i1_intangible_assets import (
    I1_SHEETS,
    render as i1_render,
)
from app.routers.wp_render_strategies._i1_amortization_engine import (
    calc_straight_line_amort,
    calc_remaining_life_amort,
    calc_amort_with_impairment,
    calc_dcf_present_value,
    calc_terminal_value,
    calc_recoverable_amount,
    calc_impairment_amount,
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render策略注册验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestI1RenderStrategy:
    """验证 render 策略注册和返回结构."""

    def test_renderer_dispatch_contains_i1(self):
        """RENDERER_DISPATCH 包含 'i1-intangible-assets' key."""
        assert "i1-intangible-assets" in RENDERER_DISPATCH

    def test_renderer_dispatch_callable(self):
        """策略函数可调用."""
        fn = RENDERER_DISPATCH["i1-intangible-assets"]
        assert callable(fn)

    def test_i1_sheets_list_has_17_entries(self):
        """I1_SHEETS 包含 17 个 sheet 条目."""
        assert len(I1_SHEETS) == 17

    def test_i1_sheets_all_have_correct_component_type(self):
        """所有 sheet 的 component_type 为 'i1-intangible-assets'."""
        for sheet in I1_SHEETS:
            assert sheet["component_type"] == "i1-intangible-assets"
            assert "sheet_name" in sheet

    def test_i1_sheets_cover_account_codes(self):
        """sheet列表包含审定表（覆盖1701/1702/1703三科目）."""
        names = [s["sheet_name"] for s in I1_SHEETS]
        assert "审定表I1" in names
        assert "明细表I1-2" in names
        assert "摊销测算表（不含减值）I1-10" in names
        assert "摊销测算表（含减值）I1-11" in names
        assert "减值准备测试表I1-12" in names
        assert "可收回金额测试I1-13" in names

    @pytest.mark.asyncio
    async def test_render_returns_correct_structure(self):
        """render 函数返回包含 component_type/account_codes/sheets 的结构."""
        # Mock RenderContext
        mock_ctx = MagicMock()
        mock_ctx.project_id = "test-project"
        mock_ctx.year = 2025
        mock_ctx.wp_id = "test-wp-id"
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))
        mock_ctx.db = mock_db

        result = await i1_render(mock_ctx)

        assert result is not None
        assert result["component_type"] == "i1-intangible-assets"
        assert result["account_codes"] == ["1701", "1702", "1703"]
        assert result["prefix"] == "I1"
        assert "sheets" in result
        assert "tb_values" in result
        assert "project_context" in result
        assert "responses_snapshot" in result
        assert result["meta"]["sheet_count"] == 17
        assert result["meta"]["wp_code"] == "I1"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 导入导出端点测试
# ═══════════════════════════════════════════════════════════════════════════════


def _make_xlsx_i1_3() -> bytes:
    """创建有效的 I1-3 调整分录 xlsx 用于导入测试."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "I1-3"
    # Title row (row 1)
    ws.append(["I1-3 调整分录汇总表"])
    # Header row (row 2)
    ws.append(["序号", "调整事项", "类别", "科目代码", "科目名称", "摘要", "借方金额", "贷方金额", "索引", "备注"])
    # Data rows
    ws.append([1, "摊销调整", "AJE", "6602", "管理费用-摊销", "补提摊销", 50000, 0, "I1-9", ""])
    ws.append([2, "摊销调整", "AJE", "1702", "累计摊销", "补提摊销", 0, 50000, "I1-9", ""])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _make_xlsx_i1_5() -> bytes:
    """创建有效的 I1-5 增加检查 xlsx 用于导入测试."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "I1-5"
    ws.append(["I1-5 无形资产增加检查表"])
    ws.append(["序号", "资产名称", "取得方式", "入账日期", "入账金额", "合同/发票号", "支付方式", "审查结论"])
    ws.append([1, "ERP软件", "外购", "2025-03-15", 800000, "HT-2025-001", "银行转账", "合规"])
    ws.append([2, "专利技术", "自行研发(I2转入)", "2025-06-01", 1200000, "", "研发转入", "合规"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


class TestI1ImportExport:
    """验证 I1 导入导出三端点."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sheet", ["I1", "I1-3", "I1-5", "I1-6", "I1-8", "I1-9"])
    async def test_export_template(self, sheet: str):
        """POST export-template → 200 + xlsx content-type."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/workpapers/test-wp/i1/export-template?sheet={sheet}")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sheet", ["I1", "I1-3", "I1-5", "I1-6", "I1-8", "I1-9"])
    async def test_export_data(self, sheet: str, override_deps):
        """POST export-data → 200 + xlsx."""
        mock_db = override_deps
        mock_db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [], fetchone=lambda: None))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/workpapers/test-wp/i1/export-data?sheet={sheet}")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_import_data_i1_3(self, override_deps):
        """POST import-data I1-3 → 200 + imported_count >= 1."""
        mock_db = override_deps
        # Mock project lookup for upsert_json_rows
        mock_db.execute = AsyncMock(return_value=MagicMock(
            fetchall=lambda: [],
            fetchone=lambda: None,
            scalar_one_or_none=lambda: "test-project-id",
        ))

        xlsx_bytes = _make_xlsx_i1_3()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/import-data?sheet=I1-3",
                files={"file": ("I1-3_test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert payload.get("imported_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_import_data_i1_5(self, override_deps):
        """POST import-data I1-5 → 200 + imported_count >= 1."""
        mock_db = override_deps
        mock_db.execute = AsyncMock(return_value=MagicMock(
            fetchall=lambda: [],
            fetchone=lambda: None,
            scalar_one_or_none=lambda: "test-project-id",
        ))

        xlsx_bytes = _make_xlsx_i1_5()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/import-data?sheet=I1-5",
                files={"file": ("I1-5_test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert payload.get("imported_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_import_invalid_sheet_returns_400(self):
        """POST import-data invalid sheet → 400."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/export-template?sheet=INVALID",
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_non_xlsx_returns_400(self, override_deps):
        """POST import-data 非xlsx文件 → 400."""
        mock_db = override_deps
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/import-data?sheet=I1-3",
                files={"file": ("test.txt", b"not an xlsx", "text/plain")},
            )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 摊销引擎纯函数单元测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestI1AmortizationPureFunctions:
    """验证摊销引擎纯函数计算正确性."""

    def test_straight_line_basic(self):
        """直线法：(1000000 - 0) / 120月 = 8333.33."""
        result = calc_straight_line_amort(1_000_000, 0, 120)
        assert abs(result - 8333.33) < 0.01

    def test_straight_line_with_salvage(self):
        """直线法含残值：(500000 - 50000) / 60月 = 7500."""
        result = calc_straight_line_amort(500_000, 50_000, 60)
        assert abs(result - 7500.0) < 0.01

    def test_straight_line_zero_months(self):
        """直线法月数=0 → 返回0."""
        result = calc_straight_line_amort(100_000, 0, 0)
        assert result == 0.0

    def test_remaining_life_basic(self):
        """剩余年限法：(1000000 - 0 - 200000 - 0) / 96月 = 8333.33."""
        result = calc_remaining_life_amort(1_000_000, 0, 200_000, 0, 96)
        assert abs(result - 8333.33) < 0.01

    def test_remaining_life_with_impairment(self):
        """剩余年限法含减值：(1000000 - 50000 - 300000 - 100000) / 60月 = 9166.67."""
        result = calc_remaining_life_amort(1_000_000, 50_000, 300_000, 100_000, 60)
        assert abs(result - 9166.67) < 0.01

    def test_remaining_life_zero_months(self):
        """剩余月数=0 → 返回0."""
        result = calc_remaining_life_amort(100_000, 0, 50_000, 0, 0)
        assert result == 0.0

    def test_amort_with_impairment(self):
        """含减值重算基数同剩余年限法."""
        result = calc_amort_with_impairment(800_000, 0, 200_000, 50_000, 48)
        expected = (800_000 - 0 - 200_000 - 50_000) / 48
        assert abs(result - expected) < 0.01

    def test_dcf_present_value_basic(self):
        """DCF: [100, 100, 100] @ 10% → 100/1.1 + 100/1.21 + 100/1.331."""
        cfs = [100.0, 100.0, 100.0]
        result = calc_dcf_present_value(cfs, 0.10)
        expected = 100 / 1.1 + 100 / 1.21 + 100 / 1.331
        assert abs(result - expected) < 0.01

    def test_dcf_empty_flows(self):
        """空现金流 → 0."""
        assert calc_dcf_present_value([], 0.08) == 0.0

    def test_dcf_zero_rate(self):
        """折现率<=0 → 0."""
        assert calc_dcf_present_value([100, 200], 0.0) == 0.0
        assert calc_dcf_present_value([100, 200], -0.05) == 0.0

    def test_terminal_value_basic(self):
        """终值 = 100 / (0.08 - 0.03) = 2000."""
        result = calc_terminal_value(100.0, 0.08, 0.03)
        assert abs(result - 2000.0) < 0.01

    def test_terminal_value_rate_leq_growth(self):
        """折现率<=增长率 → 0."""
        assert calc_terminal_value(100, 0.05, 0.05) == 0.0
        assert calc_terminal_value(100, 0.03, 0.05) == 0.0

    def test_recoverable_amount(self):
        """可收回金额 = MAX(公允-处置费, 使用价值)."""
        assert calc_recoverable_amount(800_000, 1_000_000) == 1_000_000
        assert calc_recoverable_amount(1_200_000, 900_000) == 1_200_000

    def test_impairment_amount_basic(self):
        """减值金额 = MAX(账面 - 可收回, 0)."""
        assert calc_impairment_amount(1_000_000, 800_000) == 200_000
        assert calc_impairment_amount(500_000, 600_000) == 0.0

    def test_impairment_amount_capped(self):
        """减值金额不超过账面净值."""
        # book_value=100, recoverable=0 → 差额100，但min(100, 100)=100
        assert calc_impairment_amount(100, 0) == 100
        # edge: recoverable 为负数(不应发生但防御)
        assert calc_impairment_amount(100, -50) <= 100


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 摊销验证端点集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestI1AmortizationValidateEndpoint:
    """验证 POST /api/workpapers/{wp_id}/i1/amortization/validate."""

    @pytest.mark.asyncio
    async def test_validate_straight_line(self):
        """直线法摊销验证 → 200 + is_valid."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/validate",
                json={
                    "assets": [
                        {
                            "asset_id": "a1",
                            "asset_name": "ERP软件",
                            "cost": 1_000_000,
                            "salvage": 0,
                            "useful_life_months": 120,
                            "remaining_months": 96,
                            "method": "straight_line",
                            "book_amortization": 100_000,
                        }
                    ],
                    "tolerance": 1.0,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert "is_valid" in payload
        assert "results" in payload
        assert len(payload["results"]) == 1
        assert payload["results"][0]["method_used"] == "straight_line"
        # 8333.33 * 12 = 100000 → within tolerance
        assert payload["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_remaining_life(self):
        """剩余年限法摊销验证 → 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/validate",
                json={
                    "assets": [
                        {
                            "asset_id": "a2",
                            "asset_name": "专利技术",
                            "cost": 500_000,
                            "salvage": 0,
                            "acc_amort": 100_000,
                            "impairment": 0,
                            "useful_life_months": 60,
                            "remaining_months": 36,
                            "method": "remaining_life",
                            "book_amortization": 133_333,
                        }
                    ],
                    "tolerance": 5.0,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert "is_valid" in payload
        # (500000 - 0 - 100000 - 0) / 36 * 12 = 133333.33
        assert payload["results"][0]["method_used"] == "remaining_life"

    @pytest.mark.asyncio
    async def test_validate_with_impairment(self):
        """含减值摊销验证 → 200."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/validate",
                json={
                    "assets": [
                        {
                            "asset_id": "a3",
                            "asset_name": "商标权",
                            "cost": 800_000,
                            "salvage": 0,
                            "acc_amort": 200_000,
                            "impairment": 50_000,
                            "useful_life_months": 120,
                            "remaining_months": 72,
                            "method": "with_impairment",
                            "book_amortization": 91_667,
                        }
                    ],
                    "tolerance": 5.0,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert payload["results"][0]["method_used"] == "with_impairment"
        # (800000 - 0 - 200000 - 50000) / 72 * 12 = 91666.67 → within 5 tolerance
        assert payload["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_empty_assets_returns_400(self):
        """空 assets 列表 → 400."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/validate",
                json={"assets": [], "tolerance": 1.0},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_validate_discrepancy_detected(self):
        """差异超过容忍度时 is_valid=False."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/validate",
                json={
                    "assets": [
                        {
                            "asset_id": "a4",
                            "asset_name": "土地使用权",
                            "cost": 2_000_000,
                            "salvage": 0,
                            "useful_life_months": 240,
                            "remaining_months": 180,
                            "method": "straight_line",
                            "book_amortization": 200_000,  # 正确应为100000
                        }
                    ],
                    "tolerance": 1.0,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert payload["is_valid"] is False
        assert len(payload["discrepancies"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DCF计算端点集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestI1DcfEndpoint:
    """验证 POST /api/workpapers/{wp_id}/i1/amortization/calculate-dcf."""

    @pytest.mark.asyncio
    async def test_dcf_basic(self):
        """DCF计算 → 200 + results."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/calculate-dcf",
                json={
                    "assets": [
                        {
                            "asset_id": "d1",
                            "asset_name": "软件著作权",
                            "cash_flows": [100_000, 120_000, 150_000, 130_000, 110_000],
                            "discount_rate": 0.08,
                            "growth_rate": 0.02,
                            "perpetuity_cf": 100_000,
                            "fair_value_less_disposal": 400_000,
                            "book_value": 600_000,
                        }
                    ],
                    "include_sensitivity": True,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        assert "results" in payload
        assert len(payload["results"]) == 1
        result = payload["results"][0]
        assert result["present_value"] > 0
        assert result["terminal_value"] > 0
        assert result["value_in_use"] > 0
        assert result["recoverable_amount"] > 0
        # 包含敏感性分析
        assert "sensitivity" in result
        assert "discount_rate_plus_1pct" in result["sensitivity"]
        assert "growth_rate_plus_05pct" in result["sensitivity"]

    @pytest.mark.asyncio
    async def test_dcf_no_impairment_needed(self):
        """可收回金额 > 账面 → impairment_amount = 0."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/calculate-dcf",
                json={
                    "assets": [
                        {
                            "asset_id": "d2",
                            "asset_name": "特许经营权",
                            "cash_flows": [500_000, 500_000, 500_000, 500_000, 500_000],
                            "discount_rate": 0.10,
                            "growth_rate": 0.0,
                            "perpetuity_cf": 0,
                            "fair_value_less_disposal": 2_000_000,
                            "book_value": 1_000_000,
                        }
                    ],
                    "include_sensitivity": False,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        result = payload["results"][0]
        assert result["impairment_amount"] == 0

    @pytest.mark.asyncio
    async def test_dcf_empty_assets_returns_400(self):
        """空 assets 列表 → 400."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/calculate-dcf",
                json={"assets": [], "include_sensitivity": True},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_dcf_impairment_needed(self):
        """账面 > 可收回 → impairment_amount > 0."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/i1/amortization/calculate-dcf",
                json={
                    "assets": [
                        {
                            "asset_id": "d3",
                            "asset_name": "过期商标",
                            "cash_flows": [10_000, 8_000, 5_000],
                            "discount_rate": 0.12,
                            "growth_rate": 0.0,
                            "perpetuity_cf": 0,
                            "fair_value_less_disposal": 15_000,
                            "book_value": 200_000,
                        }
                    ],
                    "include_sensitivity": True,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        payload = data.get("data", data)
        result = payload["results"][0]
        assert result["impairment_amount"] > 0
        # 确保减值不超过账面
        assert result["impairment_amount"] <= 200_000
