"""自定义函数注册签名、循环引用与嵌套 fail-closed（ADR-FHIC-17，需求 14.1/14.2，任务 33）。

端点带 ``param_names`` 注册成功；自环 / 互环 400；强注入 handler 后 ``ok=False``；参数个数不符报错。
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from app.services.formula_engine import (
    FormulaContext,
    FormulaEvalError,
    FormulaResult,
    execute,
    _REGISTRY,
)
from app.services.formula_custom_functions import (
    register_custom_function,
    unregister_custom_function,
    list_custom_functions,
    get_custom_registry,
    _nesting_depth,
)


# ── 辅助 ─────────────────────────────────────────────────────

def _empty_ctx() -> FormulaContext:
    """无任何预载数据的上下文（自定义函数只测纯求值）。"""
    return FormulaContext()


def _cleanup(*names: str):
    """注销自定义函数并从 _REGISTRY 清除（测试隔离）。"""
    for n in names:
        unregister_custom_function(n)


# ── 1. 端点带 param_names 注册成功（需求 14.1）────────────────

class TestRegisterWithParamNames:
    """验证 ``param_names`` 正常落地到注册表与 handler。"""

    def test_register_with_param_names_success(self):
        """带 param_names 注册不 500，返回 registered=True。"""
        try:
            result = register_custom_function(
                name="FHIC_T33_ADD",
                expression="1+2",
                description="测试加法",
                param_names=["a", "b"],
            )
            assert result["registered"] is True
            assert result["name"] == "FHIC_T33_ADD"

            # 注册表里有 param_names
            meta = get_custom_registry()["FHIC_T33_ADD"]
            assert meta["param_names"] == ["a", "b"]
            assert meta["expression"] == "1+2"
        finally:
            _cleanup("FHIC_T33_ADD")

    def test_register_name_uppercased(self):
        """名称统一大写。"""
        try:
            register_custom_function(name="lower_case_fn", expression="1+1")
            assert "LOWER_CASE_FN" in get_custom_registry()
            assert "LOWER_CASE_FN" in _REGISTRY.known_function_names()
        finally:
            _cleanup("LOWER_CASE_FN")

    def test_register_duplicate_param_names_rejected(self):
        """参数名重复 → ValueError。"""
        with pytest.raises(ValueError, match="重复"):
            register_custom_function(
                name="FHIC_T33_DUP",
                expression="1+1",
                param_names=["x", "x"],
            )
        assert "FHIC_T33_DUP" not in get_custom_registry()

    def test_register_empty_param_names_ok(self):
        """空 param_names（无参函数）注册成功。"""
        try:
            result = register_custom_function(
                name="FHIC_T33_NOPARAM",
                expression="42",
                param_names=[],
            )
            assert result["registered"] is True
        finally:
            _cleanup("FHIC_T33_NOPARAM")

    def test_list_custom_functions(self):
        """list_custom_functions 返回已注册的自定义函数。"""
        try:
            register_custom_function(name="FHIC_T33_LIST", expression="1+1")
            names = [f["name"] for f in list_custom_functions()]
            assert "FHIC_T33_LIST" in names
        finally:
            _cleanup("FHIC_T33_LIST")


# ── 2. 自环 / 互环 → ValueError（需求 14.1）──────────────────

class TestCycleDetection:
    """注册时检测自环与互环。"""

    def test_self_referencing_rejected(self):
        """自环（自己调用自己）→ ValueError。"""
        with pytest.raises(ValueError, match="引用自身"):
            register_custom_function(
                name="FHIC_T33_SELF",
                expression="FHIC_T33_SELF(1)",
            )
        assert "FHIC_T33_SELF" not in get_custom_registry()

    def test_mutual_cycle_rejected(self):
        """互环（A→B→A）→ ValueError。"""
        try:
            # 先注册 A，表达式里引用 B（B 不存在，所以 A 能注册）
            register_custom_function(
                name="FHIC_T33_CYC_A",
                expression="FHIC_T33_CYC_B(1) + 1",
            )
            # 注册 B，表达式引用 A → 检测到 A→B→A 环
            with pytest.raises(ValueError, match="循环引用"):
                register_custom_function(
                    name="FHIC_T33_CYC_B",
                    expression="FHIC_T33_CYC_A(2) + 2",
                )
            assert "FHIC_T33_CYC_B" not in get_custom_registry()
        finally:
            _cleanup("FHIC_T33_CYC_A", "FHIC_T33_CYC_B")

    def test_referencing_builtin_ok(self):
        """引用内置函数不算环。"""
        try:
            result = register_custom_function(
                name="FHIC_T33_BUILTIN_REF",
                expression="ABS(-5)",
            )
            assert result["registered"] is True
        finally:
            _cleanup("FHIC_T33_BUILTIN_REF")

    def test_chain_no_cycle_ok(self):
        """链式引用（A→B，B不引用A）不算环。"""
        try:
            register_custom_function(name="FHIC_T33_CHAIN_B", expression="1+1")
            result = register_custom_function(
                name="FHIC_T33_CHAIN_A",
                expression="FHIC_T33_CHAIN_B()+2",
            )
            assert result["registered"] is True
        finally:
            _cleanup("FHIC_T33_CHAIN_A", "FHIC_T33_CHAIN_B")


# ── 3. 强注入 handler 后 ok=False（需求 14.2）────────────────

class TestNestedFailClosed:
    """handler 内层失败 → 外层 FormulaEvalError → ok=False。"""

    def test_inner_error_propagates(self):
        """内层求值有错误时，handler 抛 FormulaEvalError → 外层 ok=False。"""
        try:
            # 注册一个表达式会失败的自定义函数（除零）
            register_custom_function(
                name="FHIC_T33_DIVZERO",
                expression="1/0",
            )
            ctx = _empty_ctx()
            result = execute("FHIC_T33_DIVZERO()", ctx)
            assert not result.ok, "内层除零应导致 ok=False"
            assert any("除" in e or "零" in e or "失败" in e for e in result.errors)
        finally:
            _cleanup("FHIC_T33_DIVZERO")

    def test_nesting_limit_exceeded(self):
        """嵌套深度超过上限 → ok=False。"""
        try:
            # FHIC_T33_RECURSE 自环无法注册，但可以注册两个互相不检测的函数来测试嵌套。
            # 方法：注册函数 A 的表达式为常量，然后手动替换 handler 使其递归。
            register_custom_function(
                name="FHIC_T33_NEST",
                expression="42",
            )
            # 手动替换 handler 为一个会递归调用自身的版本
            original_handler = _REGISTRY.get("FHIC_T33_NEST")

            def recursive_handler(args, ctx, trace):
                depth = _nesting_depth.get(0)
                if depth >= 8:
                    raise FormulaEvalError(f"自定义函数 FHIC_T33_NEST 嵌套深度超过上限 8")
                token = _nesting_depth.set(depth + 1)
                try:
                    result = execute("FHIC_T33_NEST()", ctx)
                    if not result.ok:
                        raise FormulaEvalError(result.errors[0] if result.errors else "内层失败")
                    return result.value
                finally:
                    _nesting_depth.reset(token)

            _REGISTRY.register("FHIC_T33_NEST", recursive_handler, category="自定义")

            ctx = _empty_ctx()
            result = execute("FHIC_T33_NEST()", ctx)
            assert not result.ok, "嵌套超限应导致 ok=False"
            assert any("嵌套" in e or "上限" in e for e in result.errors)
        finally:
            _cleanup("FHIC_T33_NEST")


# ── 4. 参数个数不符报错（需求 14.2）──────────────────────────

class TestParamCountMismatch:
    """param_names 注册后，调用参数个数不等 → FormulaEvalError。"""

    def test_too_few_args(self):
        """参数不足 → ok=False。"""
        try:
            register_custom_function(
                name="FHIC_T33_TWOPARAM",
                expression="1+2",
                param_names=["a", "b"],
            )
            ctx = _empty_ctx()
            # 只传 1 个参数（L1 求值会把 FHIC_T33_TWOPARAM(1) 解析为 1 个参数）
            result = execute("FHIC_T33_TWOPARAM(1)", ctx)
            assert not result.ok, "参数不足应导致 ok=False"
            assert any("参数" in e for e in result.errors)
        finally:
            _cleanup("FHIC_T33_TWOPARAM")

    def test_too_many_args(self):
        """参数过多 → ok=False。"""
        try:
            register_custom_function(
                name="FHIC_T33_ONEPARAM",
                expression="42",
                param_names=["x"],
            )
            ctx = _empty_ctx()
            result = execute("FHIC_T33_ONEPARAM(1, 2, 3)", ctx)
            assert not result.ok, "参数过多应导致 ok=False"
            assert any("参数" in e for e in result.errors)
        finally:
            _cleanup("FHIC_T33_ONEPARAM")

    def test_exact_param_count_ok(self):
        """参数个数正确 → ok=True。"""
        try:
            register_custom_function(
                name="FHIC_T33_EXACT",
                expression="1+1",
                param_names=["x"],
            )
            ctx = _empty_ctx()
            result = execute("FHIC_T33_EXACT(5)", ctx)
            assert result.ok, f"参数正确应 ok=True，errors={result.errors}"
        finally:
            _cleanup("FHIC_T33_EXACT")

    def test_no_param_names_any_count_ok(self):
        """无 param_names（空列表）注册的函数，任意参数个数不报错。"""
        try:
            register_custom_function(
                name="FHIC_T33_ANYPARAM",
                expression="99",
                param_names=[],
            )
            ctx = _empty_ctx()
            # 0 个参数
            r0 = execute("FHIC_T33_ANYPARAM()", ctx)
            assert r0.ok, f"无参数要求时 0 参应 ok，errors={r0.errors}"
            # 3 个参数
            r3 = execute("FHIC_T33_ANYPARAM(1, 2, 3)", ctx)
            assert r3.ok, f"无参数要求时 3 参应 ok，errors={r3.errors}"
        finally:
            _cleanup("FHIC_T33_ANYPARAM")


# ── 5. 注销与隔离 ────────────────────────────────────────────

class TestUnregisterAndIsolation:
    """注销后不再可用、_REGISTRY 同步移除。"""

    def test_unregister_removes_from_both(self):
        register_custom_function(name="FHIC_T33_REMOVE", expression="1+1")
        assert "FHIC_T33_REMOVE" in _REGISTRY.known_function_names()
        assert "FHIC_T33_REMOVE" in get_custom_registry()

        removed = unregister_custom_function("FHIC_T33_REMOVE")
        assert removed is True
        assert "FHIC_T33_REMOVE" not in _REGISTRY.known_function_names()
        assert "FHIC_T33_REMOVE" not in get_custom_registry()

    def test_unregister_nonexistent_returns_false(self):
        assert unregister_custom_function("FHIC_T33_NOEXIST") is False
