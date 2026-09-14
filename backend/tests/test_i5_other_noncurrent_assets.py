"""I5 其他非流动资产 — 后端 pytest: render策略 + 导入导出 + AI + YAML.

Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 7.3
Requirements: 1.1-1.10, 5.1-5.4

测试清单:
1. render 策略返回正确结构（component_type, account_codes, tb_values, sheets）
2. RENDERER_DISPATCH 包含 'i5-other-noncurrent-assets' key
3. 导入导出模块 imports 正确且有 router
4. AI generate 模块 imports 正确且有 router
5. YAML schema 文件存在且可解析
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._i5_other_noncurrent_assets import (
    I5_SHEETS,
    render as i5_render,
)
from app.routers.wp_render_strategies._i5_import_export import _I5_SPECS, router as ie_router
from app.routers.wp_render_strategies._i5_ai_generate import (
    _SUPPORTED_SECTIONS,
    router as ai_router,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeRenderContext:
    """最小化 RenderContext mock."""

    def __init__(self):
        self.project_id = "proj-001"
        self.wp_id = "wp-001"
        self.year = 2025
        # Mock DB: 所有 execute 返回空
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.fetchone.return_value = None
        self.db = AsyncMock()
        self.db.execute = AsyncMock(return_value=mock_result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Render 策略
# ═══════════════════════════════════════════════════════════════════════════════


class TestI5RenderStrategy:
    """验证 render 策略注册和返回结构."""

    def test_renderer_dispatch_contains_i5(self):
        """RENDERER_DISPATCH 包含 'i5-other-noncurrent-assets' key."""
        assert "i5-other-noncurrent-assets" in RENDERER_DISPATCH

    @pytest.mark.asyncio
    async def test_render_returns_correct_structure(self):
        """render() 返回正确的 html_data 结构."""
        ctx = _FakeRenderContext()
        result = await i5_render(ctx)

        assert result is not None
        assert result["component_type"] == "i5-other-noncurrent-assets"
        assert "account_codes" in result
        assert "1911" in result["account_codes"]
        assert "responses_snapshot" in result
        assert "tb_values" in result
        assert "project_context" in result
        assert "sheets" in result
        assert "meta" in result

    @pytest.mark.asyncio
    async def test_render_tb_values_is_dict(self):
        """render() 返回的 tb_values 是 dict（即使为空，数据结构正确）."""
        ctx = _FakeRenderContext()
        result = await i5_render(ctx)

        assert isinstance(result["tb_values"], dict)

    def test_i5_sheets_count(self):
        """I5_SHEETS 应有 8 个 sheet 定义（底稿目录+程序表+审定+明细+调整+检查+附注×2）."""
        assert len(I5_SHEETS) == 8

    @pytest.mark.asyncio
    async def test_render_meta_has_sheet_count(self):
        """meta.sheet_count 应为 9."""
        ctx = _FakeRenderContext()
        result = await i5_render(ctx)

        assert result["meta"]["sheet_count"] == 9
        assert result["meta"]["wp_code"] == "I5"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestI5ImportExport:
    """验证 I5 导入导出 specs 和 router."""

    def test_i5_specs_has_2_entries(self):
        """_I5_SPECS 应有 2 个条目: I5-2, I5-3."""
        assert len(_I5_SPECS) == 2
        assert "I5-2" in _I5_SPECS
        assert "I5-3" in _I5_SPECS

    def test_i5_specs_have_required_keys(self):
        """每个 spec 条目应包含必要 keys."""
        for key, spec in _I5_SPECS.items():
            assert "item_id" in spec, f"{key} missing item_id"
            assert "title" in spec, f"{key} missing title"
            assert "headers" in spec, f"{key} missing headers"
            assert "field_keys" in spec, f"{key} missing field_keys"
            assert "guidance" in spec, f"{key} missing guidance"

    def test_i5_specs_headers_keys_length_match(self):
        """每个 spec 的 headers 和 field_keys 长度应一致."""
        for key, spec in _I5_SPECS.items():
            assert len(spec["headers"]) == len(spec["field_keys"]), (
                f"{key}: headers({len(spec['headers'])}) != field_keys({len(spec['field_keys'])})"
            )

    def test_import_export_router_exists(self):
        """导入导出模块应有 router."""
        assert ie_router is not None
        assert hasattr(ie_router, "routes")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AI 辅助
# ═══════════════════════════════════════════════════════════════════════════════


class TestI5AiGenerate:
    """验证 AI generate 模块结构."""

    def test_ai_router_exists(self):
        """AI generate 模块应有 router."""
        assert ai_router is not None
        assert hasattr(ai_router, "routes")

    def test_supported_sections_count(self):
        """应支持 9 个 AI section."""
        assert len(_SUPPORTED_SECTIONS) == 9

    def test_supported_sections_names(self):
        """验证核心 section 名称包含 adjudication/note/conclusion."""
        assert "adjudication" in _SUPPORTED_SECTIONS
        assert "note" in _SUPPORTED_SECTIONS
        assert "conclusion" in _SUPPORTED_SECTIONS


# ═══════════════════════════════════════════════════════════════════════════════
# 4. YAML Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestI5YamlSchema:
    """验证 YAML schema 可解析且结构正确."""

    @pytest.fixture
    def schema(self):
        yaml_path = "backend/data/ledger_adapters/wp_render_schema/i5-other-noncurrent-assets.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_yaml_parseable(self, schema):
        """YAML 文件可正确解析."""
        assert schema is not None

    def test_yaml_component_type(self, schema):
        """component_type 应为 'i5-other-noncurrent-assets'."""
        assert schema["component_type"] == "i5-other-noncurrent-assets"

    def test_yaml_account_codes(self, schema):
        """account_codes 应包含 '1911'."""
        assert "1911" in schema["account_codes"]
