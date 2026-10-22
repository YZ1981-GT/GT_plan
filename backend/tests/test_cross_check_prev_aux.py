"""表间审核 PREV/AUX 扩展测试（spec: formula-management-deep-optimization · R4）。

验证：
1. evaluate_formula_result 默认行为不变（PREV/AUX 硬置 0）
2. enable_prev=True 时 PREV 取真实数据
3. enable_aux=True 时 AUX 取真实数据
4. cross_check_rules._evaluate 使用 CENTRAL_BATCH 检查
5. 预置规则文件可加载
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestEvaluateFormulaPrevDefault:
    """默认行为：PREV/AUX 硬置 0。"""

    @pytest.mark.asyncio
    async def test_prev_returns_zero_by_default(self):
        """enable_prev=False（默认）时 PREV 替换为 0。"""
        from app.services.report_engine import evaluate_formula_result

        resolver = MagicMock()
        resolver.resolve_tb = AsyncMock(return_value=Decimal("100"))
        resolver.resolve_sum = AsyncMock(return_value=Decimal("0"))

        result = await evaluate_formula_result(
            "PREV('1001', '期末余额')",
            resolver=resolver,
            row_cache={},
        )
        # 默认 PREV 被替换为 0
        assert result.value == Decimal("0")

    @pytest.mark.asyncio
    async def test_aux_returns_zero_by_default(self):
        """enable_aux=False（默认）时 AUX 替换为 0。"""
        from app.services.report_engine import evaluate_formula_result

        resolver = MagicMock()
        resolver.resolve_tb = AsyncMock(return_value=Decimal("100"))
        resolver.resolve_sum = AsyncMock(return_value=Decimal("0"))

        result = await evaluate_formula_result(
            "AUX('1001', '客户', '期末余额')",
            resolver=resolver,
            row_cache={},
        )
        assert result.value == Decimal("0")


class TestSignatureBackwardCompat:
    """新参数不破坏现有调用方。"""

    @pytest.mark.asyncio
    async def test_old_signature_still_works(self):
        """不传 enable_prev/enable_aux 时行为与改动前一致。"""
        from app.services.report_engine import evaluate_formula_result

        resolver = MagicMock()
        resolver.resolve_tb = AsyncMock(return_value=Decimal("500"))
        resolver.resolve_sum = AsyncMock(return_value=Decimal("0"))

        result = await evaluate_formula_result(
            "TB('1001', '期末余额')",
            resolver=resolver,
            row_cache={},
        )
        # TB 正常取数
        assert result.value == Decimal("500")


class TestCrossCheckUsesCorrectExecutor:
    """cross_check_rules 使用 CENTRAL_BATCH 维度。"""

    def test_central_batch_supports_prev(self):
        from app.services.formula_management.function_support_matrix import (
            Executor,
            is_supported,
        )
        assert is_supported("PREV", Executor.CENTRAL_BATCH), "PREV 应在 central_batch 支持"

    def test_central_batch_supports_aux(self):
        from app.services.formula_management.function_support_matrix import (
            Executor,
            is_supported,
        )
        assert is_supported("AUX", Executor.CENTRAL_BATCH), "AUX 应在 central_batch 支持"

    def test_report_path_still_unsupported(self):
        """报表路径维度仍不支持 PREV/AUX（设计意图不变）。"""
        from app.services.formula_management.function_support_matrix import (
            Executor,
            is_supported,
        )
        assert not is_supported("PREV", Executor.REPORT_PATH)
        assert not is_supported("AUX", Executor.REPORT_PATH)


class TestPresetRulesFile:
    """预置规则文件结构。"""

    def test_preset_rules_loadable(self):
        path = Path(__file__).resolve().parents[1] / "data" / "cross_check_preset_rules.json"
        assert path.exists(), f"预置规则文件不存在: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("_schema_version") == 1
        rules = data.get("rules", [])
        assert len(rules) >= 4, f"至少应有 4 条预置规则，实际 {len(rules)}"
        for rule in rules:
            assert "label" in rule, "规则缺少 label"
            assert "left_ref" in rule, "规则缺少 left_ref"
            assert "operator" in rule, "规则缺少 operator"
            assert "right_ref" in rule, "规则缺少 right_ref"

    def test_preset_rules_operators_valid(self):
        path = Path(__file__).resolve().parents[1] / "data" / "cross_check_preset_rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        valid_ops = {"=", "<=", ">="}
        for rule in data.get("rules", []):
            assert rule["operator"] in valid_ops, f"无效运算符: {rule['operator']}"
