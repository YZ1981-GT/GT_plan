"""K8 销售费用 — 集成测试：损益取数(发生额) + 实质性分析 + 截止双向 + 审定回写.

Spec: .kiro/specs/k8-selling-expenses/ Task 7.2
Validates: Requirements 2.5, 4.4, 5.4, 7.1

测试:
1. render策略结构验证（callable + income_statement标识）
2. K8_SHEETS 12 sheets 全覆盖
3. import_export路由注册（6 sheet specs: K8-2/K8-3/K8-5/K8-6/K8-7/K8-8）
4. AI生成路由注册（4 supported sections）
5. YAML schema合法性（income_statement=True, 12 sheets, account_codes=['6601']）
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from app.routers.wp_render_strategies import RENDERER_DISPATCH


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render策略结构验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK8RenderStrategy:
    """验证 K8 render策略已正确注册且结构合法."""

    def test_k8_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 k8-selling-expenses."""
        assert "k8-selling-expenses" in RENDERER_DISPATCH

    def test_k8_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._k8_selling_expenses import render

        assert callable(render)

    def test_k8_account_prefix(self):
        """科目前缀为 6601（损益类/销售费用）."""
        from app.routers.wp_render_strategies._k8_selling_expenses import _K8_ACCOUNT_PREFIX

        assert _K8_ACCOUNT_PREFIX == "6601"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. K8_SHEETS 全12 sheets定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK8Sheets:
    """验证 K8_SHEETS 包含全部12个sheet."""

    def test_k8_sheets_count(self):
        """K8_SHEETS 恰好12个sheet."""
        from app.routers.wp_render_strategies._k8_selling_expenses import K8_SHEETS

        assert len(K8_SHEETS) == 12

    def test_k8_sheets_all_have_component_type(self):
        """每个sheet都标记component_type为k8-selling-expenses."""
        from app.routers.wp_render_strategies._k8_selling_expenses import K8_SHEETS

        for sheet in K8_SHEETS:
            assert sheet["component_type"] == "k8-selling-expenses"

    def test_k8_sheets_expected_names(self):
        """K8_SHEETS包含所有预期的sheet名称."""
        from app.routers.wp_render_strategies._k8_selling_expenses import K8_SHEETS

        names = [s["sheet_name"] for s in K8_SHEETS]
        expected_keywords = [
            "底稿目录",
            "K8A",
            "K8-1",
            "K8-2",
            "K8-3",
            "K8-4",
            "K8-5",
            "K8-6",
            "K8-7",
            "K8-8",
            "上市公司",
            "国有企业",
        ]
        for kw in expected_keywords:
            assert any(kw in n for n in names), f"缺少含'{kw}'的sheet"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Import/Export路由验证（6 sheet specs）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK8ImportExport:
    """验证 K8 导入导出路由结构."""

    def test_k8_import_export_router_exists(self):
        """_k8_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._k8_import_export import router

        assert router is not None

    def test_k8_import_export_six_sheet_specs(self):
        """_K8_SPECS 包含6个sheet规格（K8-2/K8-3/K8-5/K8-6/K8-7/K8-8）."""
        from app.routers.wp_render_strategies._k8_import_export import _K8_SPECS

        expected_keys = {"K8-2", "K8-3", "K8-5", "K8-6", "K8-7", "K8-8"}
        assert set(_K8_SPECS.keys()) == expected_keys

    def test_k8_each_spec_has_required_fields(self):
        """每个sheet spec都有item_id/title/headers/field_keys/guidance."""
        from app.routers.wp_render_strategies._k8_import_export import _K8_SPECS

        for key, spec in _K8_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert "guidance" in spec, f"{key} 缺少 guidance"
            # headers 和 field_keys 长度一致
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    @pytest.mark.asyncio
    async def test_k8_export_template_route_registered(self):
        """K8 export-template 路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/k8/export-template?sheet=K8-2")
        assert resp.status_code != 404, "K8 export-template route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AI生成路由验证（4 sections）
# ═══════════════════════════════════════════════════════════════════════════════


class TestK8AiGenerate:
    """验证 K8 AI生成路由结构."""

    def test_k8_ai_router_exists(self):
        """_k8_ai_generate 模块有 router 对象."""
        from app.routers.wp_render_strategies._k8_ai_generate import router

        assert router is not None

    def test_k8_ai_four_supported_sections(self):
        """_SUPPORTED_SECTIONS 恰好包含4个section."""
        from app.routers.wp_render_strategies._k8_ai_generate import _SUPPORTED_SECTIONS

        expected = {
            "fluctuation-analysis",
            "cutoff-conclusion",
            "contract-check-eval",
            "overall-opinion",
        }
        assert _SUPPORTED_SECTIONS == expected

    @pytest.mark.asyncio
    async def test_k8_ai_generate_route_registered(self):
        """K8 AI生成路由已在 app 中注册."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/k8/ai-generate",
                json={"section": "fluctuation-analysis", "existingContent": ""},
            )
        assert resp.status_code != 404, "K8 ai-generate route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. YAML Schema验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestK8YamlSchema:
    """验证 k8-selling-expenses.yaml 结构完整性."""

    @pytest.fixture
    def schema(self):
        yaml_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "ledger_adapters"
            / "wp_render_schema"
            / "k8-selling-expenses.yaml"
        )
        assert yaml_path.exists(), f"YAML schema not found: {yaml_path}"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_income_statement_flag(self, schema):
        """income_statement=True 标识损益类."""
        assert schema["income_statement"] is True

    def test_account_codes(self, schema):
        """account_codes 包含 '6601'."""
        assert "6601" in schema["account_codes"]

    def test_component_type(self, schema):
        """component_type 为 k8-selling-expenses."""
        assert schema["component_type"] == "k8-selling-expenses"

    def test_wp_code(self, schema):
        """wp_code 为 K8."""
        assert schema["wp_code"] == "K8"

    def test_self_load(self, schema):
        """selfLoad=True."""
        assert schema["selfLoad"] is True

    def test_twelve_sheets(self, schema):
        """sheets 定义恰好12个."""
        assert len(schema["sheets"]) == 12

    def test_tb_writeback_occurrence(self, schema):
        """tb_writeback.value_type='occurrence_amount'（发生额非余额）."""
        wb = schema["tb_writeback"]
        assert wb["account_code"] == "6601"
        assert wb["value_type"] == "occurrence_amount"

    def test_cross_wp_references(self, schema):
        """cross_wp_references 存在且有引用."""
        refs = schema.get("cross_wp_references", [])
        assert len(refs) >= 3
        # 验证K8-3 → A13引用存在
        a13_refs = [r for r in refs if "A13" in r.get("target_wp", "")]
        assert len(a13_refs) >= 1, "缺少K8-3→A13交叉引用"
