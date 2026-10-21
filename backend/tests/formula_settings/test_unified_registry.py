"""统一公式注册表守卫（spec unified-formula-registry Phase 1 · Task 5）。

三项断言：
1. _REGISTRY 包含全部 20 个已知函数（含 5 个底稿占位）
2. prefill_engine._get_formula_re() 能匹配全部 20 种 =FUNC(...) 公式
3. formula_grammar.FORMULA_ARITY 与 _REGISTRY 逐键一致（不允许任一侧多出未注册函数）
"""
from __future__ import annotations

import re

import pytest

# 全部已知函数名（单一真源 = 本列表；后端 _REGISTRY 与前端 KNOWN_FUNCTIONS 必须 ⊇ 本列表）
EXPECTED_FUNCTIONS = frozenset({
    # 取数
    "TB", "SUM_TB", "PREV", "AUX", "NOTE", "WP", "ADJ",
    # 引用
    "ROW", "SUM_ROW", "REPORT",
    # 数学/逻辑
    "ABS", "ROUND", "MAX", "MIN", "IF",
    # 底稿取数（占位 handler，真实取数走 prefill_engine）
    "LEDGER", "LEDGER_DETAIL", "TB_AUX", "COUNT_LEDGER", "PLACEHOLDER",
})


class TestFunctionRegistry:
    """_REGISTRY 包含全部预期函数且不少。"""

    def test_all_expected_functions_registered(self):
        from app.services.formula_engine import _REGISTRY

        registered = _REGISTRY.known_function_names()
        missing = EXPECTED_FUNCTIONS - registered
        assert not missing, f"_REGISTRY 缺少函数：{missing}"

    def test_no_unexpected_unregistered(self):
        """_REGISTRY 不应含预期列表之外的未知函数（新增时先更新 EXPECTED_FUNCTIONS）。"""
        from app.services.formula_engine import _REGISTRY

        registered = _REGISTRY.known_function_names()
        extra = registered - EXPECTED_FUNCTIONS
        assert not extra, f"_REGISTRY 多出函数未登记到 EXPECTED_FUNCTIONS：{extra}"

    def test_each_function_has_handler(self):
        from app.services.formula_engine import _REGISTRY

        for name in EXPECTED_FUNCTIONS:
            handler = _REGISTRY.get(name)
            assert handler is not None, f"{name} 注册了但 handler 为 None"
            assert callable(handler), f"{name} 的 handler 不可调用"


class TestPrefillFormulaRE:
    """prefill_engine._get_formula_re() 能匹配全部 20 种公式。"""

    @pytest.fixture
    def pattern(self):
        from app.services.prefill_engine import _get_formula_re

        return _get_formula_re()

    @pytest.mark.parametrize("func_name", sorted(EXPECTED_FUNCTIONS))
    def test_matches_each_function(self, pattern, func_name):
        if func_name == "PLACEHOLDER":
            formula = "=PLACEHOLDER()"
        elif func_name in ("ABS", "ROW"):
            formula = f"={func_name}('arg1')"
        elif func_name in ("MAX", "MIN", "ROUND", "SUM_ROW", "SUM_TB", "TB", "REPORT", "ADJ", "PREV", "WP", "IF"):
            formula = f"={func_name}('arg1','arg2')"
        else:
            formula = f"={func_name}('arg1','arg2','arg3')"

        m = pattern.search(formula)
        assert m is not None, f"=…{func_name}(…) not matched by _get_formula_re()"
        assert m.group(1).upper() == func_name


class TestFormulaArityConsistency:
    """FORMULA_ARITY 与 _REGISTRY 逐键一致。"""

    def test_arity_keys_match_registry(self):
        from app.services.formula_engine import _REGISTRY
        from app.services.formula_grammar import FORMULA_ARITY

        registry_names = _REGISTRY.known_function_names()
        arity_names = set(FORMULA_ARITY.keys())
        assert arity_names == registry_names, (
            f"不一致：ARITY 多出 {arity_names - registry_names}，缺少 {registry_names - arity_names}"
        )

    def test_arity_values_match_registry_metadata(self):
        """对于非 [min,max] 形式的元数，FORMULA_ARITY 值应与 _REGISTRY.metadata.arity 相等。"""
        from app.services.formula_engine import _REGISTRY
        from app.services.formula_grammar import FORMULA_ARITY

        for meta in _REGISTRY.list_all():
            name = meta["name"]
            arity_val = FORMULA_ARITY.get(name)
            reg_arity = meta.get("arity")
            if isinstance(arity_val, list):
                # WP/PREV 等多元形式：registry 里只存单值，arity 是 [min, max]
                continue
            assert arity_val == reg_arity, f"{name}: ARITY={arity_val} != registry={reg_arity}"
