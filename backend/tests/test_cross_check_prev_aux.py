"""表间审核 PREV/AUX 扩展测试（spec: formula-management-deep-optimization · R4）。

验证：
1. evaluate_formula_result 对 PREV / AUX 置 0（报表域）；表间审核先经 ``_substitute_strict`` 严格代入
2. 原 ``enable_prev`` / ``enable_aux`` 两个开关已删除（formula-fetch-followup-defect-closure 6.6）：唯一调用方传 False，
   打开时 PREV 只认同项目上年、AUX 从不存在的 ``app.models.four_table_models`` 导入（恒失败被吞）—— 本文件原写
   「enable_prev=True 时 PREV 取真实数据」等两条，但从没有用例测过打开的分支
3. cross_check_rules._evaluate 使用 CENTRAL_BATCH 检查
4. 预置规则文件可加载
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
        """报表域 PREV 替换为 0。"""
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
        """报表域 AUX 替换为 0。"""
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
    """签名：TB 正常取数；半成品开关不再存在。"""

    def test_half_built_switches_are_gone(self):
        """``enable_prev`` / ``enable_aux`` 已删除，report_engine 不再从不存在的模块导入（AST，注释不算）。"""
        import ast
        import inspect

        from app.services import report_engine

        params = inspect.signature(report_engine.evaluate_formula_result).parameters
        assert "enable_prev" not in params and "enable_aux" not in params
        tree = ast.parse(inspect.getsource(report_engine))
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert "app.models.four_table_models" not in modules, "report_engine 又从不存在的 four_table_models 导入"

    @pytest.mark.asyncio
    async def test_old_signature_still_works(self):
        """不传额外参数时 TB 正常取数。"""
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


class TestCrossCheckStrictCrossRefs:
    """表间审核对 WP / NOTE 严格取数：取不到如实记为不通过，不按 0 去比（``strict_context=True``）。

    报表域对取不到的 WP / NOTE 按 0 求值；表间审核若也按 0，左右两边都缺数时「0 = 0」恒通过。
    """

    @staticmethod
    def _resolver():
        from types import SimpleNamespace
        from uuid import uuid4

        async def _zero(*_a, **_k):
            return Decimal("0")

        return SimpleNamespace(db=None, project_id=uuid4(), year=2025, resolve_tb=_zero, resolve_sum=_zero)

    @pytest.mark.asyncio
    async def test_unavailable_wp_is_not_compared_as_zero(self, monkeypatch):
        from app.services import formula_engine
        from app.services.formula_settings.cross_check_rules import _evaluate

        async def _none(*_a, **_k):
            return None

        monkeypatch.setattr(formula_engine.WPExecutor, "execute", staticmethod(_none))
        value, reason = await _evaluate("WP('E1','审定数') - 0", self._resolver(), {})
        assert value is None, f"取不到的 WP 被当成 0 参与比较：{value}"
        assert "WP('E1', '审定数')" in reason and "无可用上下文数据" in reason, reason

    @pytest.mark.asyncio
    async def test_unavailable_note_is_not_compared_as_zero(self, monkeypatch):
        """NOTE 走唯一实现 ``formula_ref_preload.load_note_values``（原先经 NOTEExecutor：未导入 sa ⇒ 恒 0，
        本用例 mock 掉它反而测不出来；spec formula-fetch-followup-defect-closure 7.2 改写）。真库口径见
        ``formula_settings/test_note_value_single_source.py``。"""
        from app.services import formula_ref_preload
        from app.services.formula_settings.cross_check_rules import _evaluate

        async def _missing(_db, _pid, _year, refs):
            return {}, {ref: "本年度（2025）附注没有章节 五、1" for ref in refs}

        monkeypatch.setattr(formula_ref_preload, "load_note_values", _missing)
        value, reason = await _evaluate("NOTE('五、1','期末余额') - 0", self._resolver(), {})
        assert value is None, f"取不到的 NOTE 被当成 0 参与比较：{value}"
        assert "NOTE('五、1','期末余额')" in reason and "附注没有章节 五、1" in reason, reason


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
