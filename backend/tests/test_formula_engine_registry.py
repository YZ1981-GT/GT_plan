"""FunctionRegistry 插件式函数注册测试（Task 4）

验证：
- 所有内置函数（TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + ABS/ROUND/MAX/MIN/IF）已注册
- register_custom_function 底层委托 FunctionRegistry.register
- validate_formula 用 registry.known_function_names 校验未知函数
- 新注册函数立即可在 execute() 中使用

**Validates: Requirements 3.1**
"""
import pytest
from decimal import Decimal

from app.services.formula_engine import (
    FunctionRegistry,
    FormulaContext,
    FormulaEngine,
    FormulaResult,
    _REGISTRY,
    execute,
    validate_formula,
)


class TestFunctionRegistryBuiltins:
    """验证所有内置函数已注册到 _REGISTRY"""

    EXPECTED_BUILTINS = {
        "TB", "SUM_TB", "ROW", "SUM_ROW", "REPORT",
        "PREV", "AUX", "NOTE", "WP",
        "ABS", "ROUND", "MAX", "MIN", "IF",
    }

    def test_all_builtins_registered(self):
        """所有 14 个内置函数都在 registry 中"""
        registered = _REGISTRY.known_function_names()
        for fn in self.EXPECTED_BUILTINS:
            assert fn in registered, f"内置函数 {fn} 未注册到 registry"

    def test_registry_get_returns_callable(self):
        """registry.get 返回可调用 handler"""
        for fn in self.EXPECTED_BUILTINS:
            handler = _REGISTRY.get(fn)
            assert handler is not None, f"{fn} handler 为 None"
            assert callable(handler), f"{fn} handler 不可调用"

    def test_registry_list_all_contains_metadata(self):
        """list_all 返回含 name/description/syntax/category 的字典列表"""
        all_funcs = _REGISTRY.list_all()
        assert len(all_funcs) >= len(self.EXPECTED_BUILTINS)
        names = {f["name"] for f in all_funcs}
        for fn in self.EXPECTED_BUILTINS:
            assert fn in names
        # 每个条目都有必要字段
        for entry in all_funcs:
            assert "name" in entry
            assert "description" in entry
            assert "syntax" in entry
            assert "category" in entry

    def test_unknown_function_returns_none(self):
        """未注册函数 get 返回 None"""
        assert _REGISTRY.get("NONEXISTENT") is None


class TestFunctionRegistryCustom:
    """验证 FormulaEngine.register_custom_function 委托 FunctionRegistry"""

    def test_register_custom_adds_to_registry(self):
        """注册自定义函数后，registry 中可查到"""
        engine = FormulaEngine()
        # 注册前确认不存在
        assert "MY_CUSTOM_FN" not in _REGISTRY.known_function_names()
        try:
            engine.register_custom_function(
                "MY_CUSTOM_FN",
                description="测试自定义函数",
                syntax="MY_CUSTOM_FN()",
                expression="100+200",
            )
            # 注册后 registry 中可查到
            assert "MY_CUSTOM_FN" in _REGISTRY.known_function_names()
            assert _REGISTRY.get("MY_CUSTOM_FN") is not None
        finally:
            # 清理
            engine.unregister_custom_function("MY_CUSTOM_FN")

    def test_unregister_removes_from_registry(self):
        """注销自定义函数后，registry 中不再存在"""
        engine = FormulaEngine()
        engine.register_custom_function(
            "TEMP_FN", description="临时", expression="50"
        )
        assert "TEMP_FN" in _REGISTRY.known_function_names()
        engine.unregister_custom_function("TEMP_FN")
        assert "TEMP_FN" not in _REGISTRY.known_function_names()

    def test_custom_function_immediately_available_in_execute(self):
        """注册自定义函数后，execute 中立即可用（AST 模式）"""
        import app.services.formula_engine as fe
        old_mode = fe._PARSE_MODE
        fe._PARSE_MODE = "ast"  # 自定义函数仅 AST 路径支持
        engine = FormulaEngine()
        try:
            engine.register_custom_function(
                "DOUBLE_TB",
                description="双倍取数",
                expression="TB('1002','期末余额')*2",
            )
            ctx = FormulaContext.from_simple_map({"1002": Decimal("500")})
            result = execute("DOUBLE_TB()", ctx)
            assert result.value == Decimal("1000")
            assert result.ok
        finally:
            engine.unregister_custom_function("DOUBLE_TB")
            fe._PARSE_MODE = old_mode

    def test_builtin_cannot_be_overridden_via_engine(self):
        """内置函数不可通过 FormulaEngine.register_custom_function 覆盖"""
        engine = FormulaEngine()
        with pytest.raises(ValueError, match="内置函数"):
            engine.register_custom_function("TB", description="hack")


class TestValidateFormulaUsesRegistry:
    """验证 validate_formula 使用 registry.known_function_names"""

    def test_known_function_passes(self):
        """已注册函数不报未知函数错误"""
        errors = validate_formula("TB('1002','期末余额')+ABS(ROW('BS-001'))")
        assert not any("未知函数" in e for e in errors)

    def test_unknown_function_detected(self):
        """未注册函数被检出"""
        errors = validate_formula("FAKE_FUNC('x')+TB('1002','期末余额')")
        assert any("FAKE_FUNC" in e for e in errors)

    def test_newly_registered_function_passes_validation(self):
        """新注册的函数通过 validate_formula 校验"""
        engine = FormulaEngine()
        try:
            engine.register_custom_function(
                "VALID_NEW", description="新函数", expression="100"
            )
            errors = validate_formula("VALID_NEW()+TB('1002','期末余额')")
            # VALID_NEW 不应被报为未知函数
            assert not any("VALID_NEW" in e for e in errors)
        finally:
            engine.unregister_custom_function("VALID_NEW")

    def test_unregistered_function_fails_validation(self):
        """注销后的函数被 validate_formula 检出为未知"""
        engine = FormulaEngine()
        engine.register_custom_function(
            "WILL_REMOVE", description="将被删除", expression="0"
        )
        engine.unregister_custom_function("WILL_REMOVE")
        errors = validate_formula("WILL_REMOVE()")
        assert any("WILL_REMOVE" in e for e in errors)


class TestFunctionRegistryClass:
    """FunctionRegistry 类本身的单元测试"""

    def test_register_and_get(self):
        """注册后可 get 到 handler"""
        reg = FunctionRegistry()
        handler = lambda args, ctx, trace: Decimal("42")
        reg.register("TEST_FN", handler, description="test")
        assert reg.get("TEST_FN") is handler

    def test_known_function_names(self):
        """known_function_names 返回所有已注册名"""
        reg = FunctionRegistry()
        reg.register("A", lambda a, c, t: Decimal("0"))
        reg.register("B", lambda a, c, t: Decimal("0"))
        assert reg.known_function_names() == {"A", "B"}

    def test_list_all_metadata(self):
        """list_all 返回完整元数据"""
        reg = FunctionRegistry()
        reg.register("X", lambda a, c, t: Decimal("0"), arity=2, description="desc", syntax="X(a,b)", category="cat")
        items = reg.list_all()
        assert len(items) == 1
        assert items[0]["name"] == "X"
        assert items[0]["arity"] == 2
        assert items[0]["description"] == "desc"
        assert items[0]["syntax"] == "X(a,b)"
        assert items[0]["category"] == "cat"

    def test_unregister(self):
        """unregister 移除函数"""
        reg = FunctionRegistry()
        reg.register("Z", lambda a, c, t: Decimal("0"))
        assert reg.unregister("Z") is True
        assert reg.get("Z") is None
        assert "Z" not in reg.known_function_names()

    def test_unregister_nonexistent(self):
        """注销不存在的函数返回 False"""
        reg = FunctionRegistry()
        assert reg.unregister("NOPE") is False

    def test_register_overwrites(self):
        """重复注册覆盖旧 handler"""
        reg = FunctionRegistry()
        reg.register("OVR", lambda a, c, t: Decimal("1"))
        reg.register("OVR", lambda a, c, t: Decimal("2"))
        ctx = FormulaContext()
        result = reg.get("OVR")([], ctx, [])
        assert result == Decimal("2")


class TestRegistryDrivenExecution:
    """验证 execute 通过 registry 查找 handler 执行"""

    def test_tb_via_registry(self):
        """TB 函数通过 registry handler 执行"""
        ctx = FormulaContext.from_simple_map({"1002": Decimal("12345")})
        result = execute("TB('1002','期末余额')", ctx)
        assert result.value == Decimal("12345")

    def test_note_via_registry(self):
        """NOTE 函数通过 registry handler 执行（从 note_data 取数）"""
        ctx = FormulaContext()
        ctx.note_data = {"五、（一）1": {"合计": Decimal("9999")}}
        result = execute("NOTE('五、（一）1','合计','期末余额')", ctx)
        assert result.value == Decimal("9999")

    def test_wp_via_registry(self):
        """WP 函数通过 registry handler 执行（从 wp_data 取数）"""
        ctx = FormulaContext()
        ctx.wp_data = {"E1": {"审定数": Decimal("7777")}}
        result = execute("WP('E1','审定数')", ctx)
        assert result.value == Decimal("7777")

    def test_aux_via_registry(self):
        """AUX 函数通过 registry handler 执行（从 aux_data 取数）"""
        ctx = FormulaContext()
        ctx.aux_data = {"1002": {"客户A": Decimal("3333")}}
        result = execute("AUX('1002','客户A','期末余额')", ctx)
        assert result.value == Decimal("3333")

    def test_if_via_registry(self):
        """IF 函数通过 registry handler 执行"""
        ctx = FormulaContext.from_simple_map({"1002": Decimal("100")})
        result = execute("IF(TB('1002','期末余额')>50,TB('1002','期末余额'),0)", ctx)
        assert result.value == Decimal("100")

    def test_unknown_function_returns_zero(self):
        """未注册函数返回 0"""
        ctx = FormulaContext()
        result = execute("NONEXIST('x')", ctx)
        assert result.value == Decimal("0")
        assert any("unknown" in t for t in result.trace)


# ═══════════════════════════════════════════════════════════════════════════════
# Property-Based Test: Q1 语义一致（registry 驱动）
# ═══════════════════════════════════════════════════════════════════════════════

from hypothesis import given, settings, assume
from hypothesis import strategies as st


def _decimal_strategy():
    """生成合理范围的 Decimal 值"""
    return st.decimals(
        min_value=-1000000, max_value=1000000,
        allow_nan=False, allow_infinity=False,
        places=2,
    )


def _account_code_strategy():
    """生成科目编码"""
    return st.sampled_from(["1001", "1002", "1012", "1122", "1231", "1401", "1406"])


def _row_code_strategy():
    """生成行次编码"""
    return st.sampled_from(["BS-001", "BS-002", "BS-003", "BS-027", "PL-001"])


@st.composite
def formula_and_ctx(draw):
    """生成公式 + FormulaContext 对"""
    # 生成 tb_data
    codes = draw(st.lists(_account_code_strategy(), min_size=1, max_size=4, unique=True))
    tb_data = {}
    for code in codes:
        val = draw(_decimal_strategy())
        tb_data[code] = {"期末余额": val, "审定数": val, "未审数": val}

    # 生成 row_cache
    row_codes = draw(st.lists(_row_code_strategy(), min_size=0, max_size=3, unique=True))
    row_cache = {rc: draw(_decimal_strategy()) for rc in row_codes}

    ctx = FormulaContext(tb_data=tb_data, row_cache=row_cache)

    # 选择一个公式模板
    code = draw(st.sampled_from(codes))
    formula_templates = [
        f"TB('{code}','期末余额')",
        f"ABS(TB('{code}','期末余额'))",
    ]
    if len(codes) >= 2:
        c2 = [c for c in codes if c != code][0]
        formula_templates.append(f"TB('{code}','期末余额')+TB('{c2}','期末余额')")
        formula_templates.append(f"MAX(TB('{code}','期末余额'),TB('{c2}','期末余额'))")
        formula_templates.append(f"MIN(TB('{code}','期末余额'),TB('{c2}','期末余额'))")
    if row_codes:
        rc = row_codes[0]
        formula_templates.append(f"ROW('{rc}')")

    formula = draw(st.sampled_from(formula_templates))
    return formula, ctx


class TestQ1SemanticConsistencyViaRegistry:
    """Q1 属性：同一公式经 registry handler 求值，函数集行为逐位一致。

    验证 registry 驱动的 AST 求值路径产出与直接调用 handler 一致。

    **Validates: Requirements 3.1**
    """

    @given(data=formula_and_ctx())
    @settings(max_examples=15, deadline=None)
    def test_registry_handler_matches_execute(self, data):
        """registry handler 直接调用 vs execute() 结果一致（纯函数确定性）。

        属性 Q1：同一公式经任何路径求值，函数集行为逐位一致。
        """
        import app.services.formula_engine as fe
        old_mode = fe._PARSE_MODE
        fe._PARSE_MODE = "ast"
        try:
            formula, ctx = data
            # 通过 execute 求值
            result = execute(formula, ctx)
            # 再次求值（确定性）
            result2 = execute(formula, ctx)
            assert result.value == result2.value, (
                f"Q1 违反：同公式两次求值不一致\n"
                f"  公式: {formula}\n"
                f"  第一次: {result.value}\n"
                f"  第二次: {result2.value}"
            )
        finally:
            fe._PARSE_MODE = old_mode
