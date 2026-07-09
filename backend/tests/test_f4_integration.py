"""F4 应付账款 — 后端集成测试：负债类期末余额 + 审定回写 + 导入导出 + AI生成.

Spec: .kiro/specs/f4-accounts-payable/ Task 7.2
Validates: Requirements 2.5, 4.3, 6.1

测试:
1. render策略从tb_balance取期末余额（贷方/负债类科目2202）
2. 审定回写期末余额到trial_balance（handler正则^[D-N]\\d+-1$匹配F4-1）
3. wp_code_overrides映射（12个F4编码→f4-accounts-payable）
4. Import/Export路由验证（12个sheet specs）
5. AI生成路由验证
6. F4_SHEETS定义验证（12 sheets）
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
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
# 1. Render策略验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4RenderStrategy:
    """验证 F4 render策略：负债类(贷方)科目2202，从tb_balance取期末余额."""

    def test_f4_registered_in_dispatch(self):
        """RENDERER_DISPATCH 包含 'f4-accounts-payable'."""
        assert "f4-accounts-payable" in RENDERER_DISPATCH

    def test_f4_render_is_callable(self):
        """render 函数可调用."""
        from app.routers.wp_render_strategies._f4_accounts_payable import render

        assert callable(render)

    @pytest.mark.asyncio
    async def test_render_returns_correct_structure(self):
        """render 返回正确结构 (component_type, account_code='2202', prefix='F4', sheets, responses_snapshot)."""
        from app.routers.wp_render_strategies._f4_accounts_payable import render

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        ctx = MagicMock()
        ctx.db = mock_db
        ctx.project_id = "test-project"
        ctx.year = 2025
        ctx.wp_id = "test-wp-id"

        result = await render(ctx)

        assert result is not None
        assert result["component_type"] == "f4-accounts-payable"
        assert result["account_code"] == "2202"
        assert result["prefix"] == "F4"
        assert result["sheets"] is not None
        assert "responses_snapshot" in result

    def test_f4_sheets_count_is_12(self):
        """F4_SHEETS 恰好12个sheet."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        assert len(F4_SHEETS) == 12


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 审定回写验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4TbWriteback:
    """验证F4审定回写逻辑：F4-1审定→trial_balance（负债类/贷方/期末余额）."""

    _PATTERN = re.compile(r"^[D-N]\d+-1$")

    def test_regex_matches_f4_1(self):
        """handler正则 ^[D-N]\\d+-1$ 匹配 F4-1."""
        assert self._PATTERN.match("F4-1"), "F4-1应通过审定表回写正则"

    def test_regex_rejects_non_audit_sheets(self):
        """拒绝非审定表编码 (F4A, F4-2, F4-3...F4-9, F4)."""
        non_audit = ["F4A", "F4-2", "F4-3", "F4-4", "F4-5", "F4-6", "F4-7", "F4-8", "F4-9", "F4"]
        for code in non_audit:
            assert not self._PATTERN.match(code), f"{code}不应匹配审定表正则"

    def test_handler_source_uses_correct_pattern(self):
        """handler源码包含该正则 ^[D-N]\\d+-1$."""
        from app.services import event_handlers_cycle_linkage

        src = inspect.getsource(event_handlers_cycle_linkage)
        assert r'^[D-N]\d+-1$' in src, (
            "handler源码中未找到正则 ^[D-N]\\d+-1$"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. wp_code_overrides映射验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4WpCodeOverrides:
    """验证 wp_code_overrides.json 中F4的12个编码映射."""

    @pytest.fixture
    def overrides(self):
        overrides_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "data"
            / "wp_code_overrides.json"
        )
        assert overrides_path.exists(), f"wp_code_overrides.json not found: {overrides_path}"
        with open(overrides_path, encoding="utf-8") as f:
            return json.load(f)

    def test_all_12_f4_codes_mapped(self, overrides):
        """全部12个F4编码映射到 'f4-accounts-payable'."""
        expected_codes = [
            "F4A", "F4-1", "F4-2", "F4-3", "F4-4", "F4-5",
            "F4-6", "F4-7", "F4-8", "F4-9", "F4-note-listed", "F4-note-soe",
        ]
        for code in expected_codes:
            assert code in overrides, f"wp_code_overrides缺少 {code}"
            assert overrides[code] == "f4-accounts-payable", (
                f"{code} 应映射到 f4-accounts-payable，实际为 {overrides[code]}"
            )

    def test_no_extra_f4_codes(self, overrides):
        """不应有意外的F4编码."""
        f4_keys = [k for k in overrides if k.startswith("F4")]
        assert len(f4_keys) == 12, f"应有12个F4编码，实际有 {len(f4_keys)}: {f4_keys}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Import/Export路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4ImportExport:
    """验证 F4 导入导出路由结构."""

    def test_f4_import_export_router_exists(self):
        """_f4_import_export 模块有 router 对象."""
        from app.routers.wp_render_strategies._f4_import_export import router

        assert router is not None

    def test_f4_import_export_sheet_specs(self):
        """包含预期的12个sheet specs."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        expected_keys = {
            "F4-2", "F4-3", "F4-5", "F4-6",
            "F4-7-purchase", "F4-7-inbound", "F4-7-invoice",
            "F4-8-debit", "F4-8-credit",
            "F4-9-factoring", "F4-9-note", "F4-9-supply",
        }
        assert set(_F4_SPECS.keys()) == expected_keys

    def test_f4_each_spec_has_required_fields(self):
        """每个spec有 item_id/title/headers/field_keys."""
        from app.routers.wp_render_strategies._f4_import_export import _F4_SPECS

        for key, spec in _F4_SPECS.items():
            assert "item_id" in spec, f"{key} 缺少 item_id"
            assert "title" in spec, f"{key} 缺少 title"
            assert "headers" in spec, f"{key} 缺少 headers"
            assert "field_keys" in spec, f"{key} 缺少 field_keys"
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    @pytest.mark.asyncio
    async def test_f4_export_template_route_registered(self):
        """export-template 路由注册 (POST /api/workpapers/test-wp/f4/export-template?sheet=F4-2, 非404)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/workpapers/test-wp/f4/export-template?sheet=F4-2")
        assert resp.status_code != 404, "F4 export-template route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. AI生成路由验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4AiGenerate:
    """验证 F4 AI生成路由结构."""

    def test_f4_ai_router_exists(self):
        """_f4_accounts_payable_ai 模块有 router 对象."""
        from app.routers.wp_render_strategies._f4_accounts_payable_ai import router

        assert router is not None

    @pytest.mark.asyncio
    async def test_f4_ai_generate_route_registered(self):
        """ai-generate 路由注册 (POST /api/workpapers/test-wp/f4/ai-generate, 非404)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/workpapers/test-wp/f4/ai-generate",
                json={"section": "substantive-analysis", "existingContent": ""},
            )
        assert resp.status_code != 404, "F4 ai-generate route not registered"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. F4_SHEETS定义验证
# ═══════════════════════════════════════════════════════════════════════════════


class TestF4Sheets:
    """验证 F4_SHEETS 定义结构."""

    def test_f4_sheets_count(self):
        """F4_SHEETS 恰好12个sheet."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        assert len(F4_SHEETS) == 12

    def test_f4_sheets_expected_names(self):
        """包含所有预期名称: F4A/F4-1~F4-9/附注披露(上市)/附注披露(国企)."""
        from app.routers.wp_render_strategies._f4_accounts_payable import F4_SHEETS

        expected_keywords = [
            "F4A", "F4-1", "F4-2", "F4-3", "F4-4",
            "F4-5", "F4-6", "F4-7", "F4-8", "F4-9",
            "附注披露(上市)", "附注披露(国企)",
        ]
        for kw in expected_keywords:
            assert kw in F4_SHEETS, f"F4_SHEETS 缺少 '{kw}'"
