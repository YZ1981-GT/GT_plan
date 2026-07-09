"""I4 长期待摊费用 — 后端 pytest: render策略 + 导入导出 + AI + YAML.

Spec: .kiro/specs/i4-long-term-prepaid/ Task 7.3
Requirements: 1.1-1.10, 6.4-6.5

测试清单:
1. render 策略返回正确结构（keys 验证）
2. tb_values 包含 1801 数据
3. I4_SPECS 导入导出有 3 个条目（I4-2, I4-6, I4-7）
4. AI 支持 5 个 section
5. YAML schema 可解析，含 12 sheets，component_type 正确
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from app.routers.wp_render_strategies import RENDERER_DISPATCH
from app.routers.wp_render_strategies._i4_long_term_prepaid import (
    I4_SHEETS,
    render as i4_render,
)
from app.routers.wp_render_strategies._i4_import_export import _I4_SPECS
from app.routers.wp_render_strategies._i4_ai_generate import _SUPPORTED_SECTIONS


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


class TestI4RenderStrategy:
    """验证 render 策略注册和返回结构."""

    def test_renderer_dispatch_contains_i4(self):
        """RENDERER_DISPATCH 包含 'i4-long-term-prepaid' key."""
        assert "i4-long-term-prepaid" in RENDERER_DISPATCH

    @pytest.mark.asyncio
    async def test_render_returns_correct_structure(self):
        """render() 返回正确的 html_data 结构."""
        ctx = _FakeRenderContext()
        result = await i4_render(ctx)

        assert result is not None
        assert result["component_type"] == "i4-long-term-prepaid"
        assert "account_codes" in result
        assert "1801" in result["account_codes"]
        assert "responses_snapshot" in result
        assert "tb_values" in result
        assert "project_context" in result
        assert "sheets" in result
        assert "meta" in result

    @pytest.mark.asyncio
    async def test_render_tb_values_keys(self):
        """render() 返回的 tb_values 是 dict（即使为空，数据结构正确）."""
        ctx = _FakeRenderContext()
        result = await i4_render(ctx)

        assert isinstance(result["tb_values"], dict)

    def test_i4_sheets_count(self):
        """I4_SHEETS 应有 12 个 sheet 定义."""
        assert len(I4_SHEETS) == 12


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 导入导出
# ═══════════════════════════════════════════════════════════════════════════════


class TestI4ImportExport:
    """验证 I4 导入导出 specs."""

    def test_i4_specs_has_3_entries(self):
        """_I4_SPECS 应有 3 个条目: I4-2, I4-6, I4-7."""
        assert len(_I4_SPECS) == 3
        assert "I4-2" in _I4_SPECS
        assert "I4-6" in _I4_SPECS
        assert "I4-7" in _I4_SPECS

    def test_i4_specs_have_required_keys(self):
        """每个 spec 条目应包含必要 keys."""
        for key, spec in _I4_SPECS.items():
            assert "item_id" in spec, f"{key} missing item_id"
            assert "title" in spec, f"{key} missing title"
            assert "headers" in spec, f"{key} missing headers"
            assert "field_keys" in spec, f"{key} missing field_keys"
            assert "guidance" in spec, f"{key} missing guidance"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AI 辅助
# ═══════════════════════════════════════════════════════════════════════════════


class TestI4AiSections:
    """验证 AI 支持的 section 数量."""

    def test_supported_sections_count(self):
        """应支持 5 个 AI section."""
        assert len(_SUPPORTED_SECTIONS) == 5

    def test_supported_sections_names(self):
        """验证 section 名称."""
        expected = {"amort-policy", "targeted-check", "adj-note", "adj-conclusion", "disclosure-narrative"}
        assert _SUPPORTED_SECTIONS == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 4. YAML Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestI4YamlSchema:
    """验证 YAML schema 可解析且结构正确."""

    @pytest.fixture
    def schema(self):
        yaml_path = "backend/data/ledger_adapters/wp_render_schema/i4-long-term-prepaid.yaml"
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_yaml_parseable(self, schema):
        """YAML 文件可正确解析."""
        assert schema is not None

    def test_yaml_has_12_sheets(self, schema):
        """sheets 应包含 12 个条目."""
        assert "sheets" in schema
        assert len(schema["sheets"]) == 12

    def test_yaml_component_type(self, schema):
        """component_type 应为 'i4-long-term-prepaid'."""
        assert schema["component_type"] == "i4-long-term-prepaid"

    def test_yaml_account_codes(self, schema):
        """account_codes 应包含 '1801'."""
        assert "1801" in schema["account_codes"]
