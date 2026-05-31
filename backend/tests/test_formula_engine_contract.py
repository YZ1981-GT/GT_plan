"""阶段 0 — L1 内核 API 契约测试

spec: formula-engine-unification / tasks.md Task 2「确立 L1 内核 API 契约」
Validates: Requirements 3.3, 3.4  |  关联属性: Q2（确定性）

═══════════════════════════════════════════════════════════════════════════════
目的
═══════════════════════════════════════════════════════════════════════════════
固化升级后的 L1 内核公开契约（设计 §四 组件 1）：
  1. FormulaResult 含 value / errors / warnings / trace 四字段 + ok 只读属性
  2. FormulaContext 含 6 个数据字段（tb_data / row_cache / prior_tb_data
     + 新增 note_data / wp_data / aux_data）+ default_column，全部默认空
  3. execute(formula, ctx) -> FormulaResult 是唯一内核入口，且为纯函数
     （需求 3.3：无 DB/async 耦合；属性 Q2：同 formula + 同 ctx → 同 FormulaResult）
  4. from_simple_map 向后兼容构造方法保留（基线测试依赖）

本测试只锁契约形状与确定性，不改求值语义（D1/D2 分歧由 baseline 测试守门）。
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_engine import (
    execute,
    FormulaContext,
    FormulaResult,
    safe_eval_expr,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FormulaResult 契约：value / errors / warnings / trace + ok
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormulaResultContract:
    def test_has_all_four_fields_with_defaults(self):
        r = FormulaResult()
        # 四字段齐全且类型/默认值正确
        assert r.value == Decimal("0")
        assert r.errors == []
        assert r.warnings == []
        assert r.trace == []

    def test_field_names_frozen(self):
        names = {f.name for f in dataclasses.fields(FormulaResult)}
        assert {"value", "errors", "warnings", "trace"} <= names

    def test_ok_property_reflects_errors(self):
        ok_result = FormulaResult(value=Decimal("1"))
        assert ok_result.ok is True

        bad_result = FormulaResult(errors=["boom"])
        assert bad_result.ok is False

    def test_default_lists_are_independent(self):
        """default_factory 不应在实例间共享同一 list 对象。"""
        a = FormulaResult()
        b = FormulaResult()
        a.errors.append("x")
        assert b.errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FormulaContext 契约：6 个数据字段 + default_column，全默认空
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormulaContextContract:
    def test_has_all_data_fields_with_empty_defaults(self):
        ctx = FormulaContext()
        assert ctx.tb_data == {}
        assert ctx.row_cache == {}
        assert ctx.prior_tb_data == {}
        # 新增三字段（Task 2）
        assert ctx.note_data == {}
        assert ctx.wp_data == {}
        assert ctx.aux_data == {}
        assert ctx.default_column == "期末余额"

    def test_new_fields_present_in_dataclass(self):
        names = {f.name for f in dataclasses.fields(FormulaContext)}
        assert {"note_data", "wp_data", "aux_data"} <= names
        # 既有字段不可丢失
        assert {"tb_data", "row_cache", "prior_tb_data", "default_column"} <= names

    def test_accepts_new_fields_as_kwargs(self):
        ctx = FormulaContext(
            note_data={"FN-01": {"合计": Decimal("100")}},
            wp_data={"E-01": {"审定数": Decimal("200")}},
            aux_data={"1122": {"客户A": Decimal("300")}},
        )
        assert ctx.note_data["FN-01"]["合计"] == Decimal("100")
        assert ctx.wp_data["E-01"]["审定数"] == Decimal("200")
        assert ctx.aux_data["1122"]["客户A"] == Decimal("300")

    def test_from_simple_map_preserved(self):
        """基线测试依赖此构造方法，必须保留且行为不变。"""
        ctx = FormulaContext.from_simple_map(
            {"1002": Decimal("100000")},
            row_cache={"BS-001": Decimal("5")},
            prior_map={"1002": Decimal("80000")},
        )
        assert ctx.tb_data["1002"]["期末余额"] == Decimal("100000")
        assert ctx.row_cache["BS-001"] == Decimal("5")
        assert ctx.prior_tb_data["1002"]["期末余额"] == Decimal("80000")
        # 新字段在 from_simple_map 路径下默认空
        assert ctx.note_data == {}
        assert ctx.wp_data == {}
        assert ctx.aux_data == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. execute 是唯一内核入口，返回 FormulaResult（需求 3.3/3.4）
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecuteEntryPoint:
    def test_returns_formula_result(self):
        ctx = FormulaContext.from_simple_map({"1002": Decimal("100")})
        r = execute("TB('1002','期末余额')", ctx)
        assert isinstance(r, FormulaResult)
        assert r.value == Decimal("100")

    def test_empty_formula_returns_ok_zero(self):
        r = execute("", FormulaContext())
        assert isinstance(r, FormulaResult)
        assert r.value == Decimal("0")
        assert r.ok

    def test_none_formula_returns_ok_zero(self):
        r = execute(None, FormulaContext())
        assert r.value == Decimal("0")
        assert r.ok

    def test_pure_function_no_db_or_async(self):
        """需求 3.3：execute 是纯函数，签名不含 db/async（不是协程）。"""
        import inspect

        assert not inspect.iscoroutinefunction(execute)
        params = set(inspect.signature(execute).parameters)
        assert params == {"formula", "ctx"}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 属性 Q2 — 确定性：同 formula + 同 ctx → 同 FormulaResult（纯函数）
#    **Validates: Requirements 3.3**
# ═══════════════════════════════════════════════════════════════════════════════

# 复用代表性公式 + 数据，覆盖 TB/SUM_TB/ROW/算术等核心路径
_Q2_TB = {
    "1002": Decimal("100000"),
    "1012": Decimal("50000"),
    "1122": Decimal("500000"),
    "1231": Decimal("-30000"),
    "1401": Decimal("10000"),
}
_Q2_ROWS = {"BS-002": Decimal("100"), "BS-027": Decimal("1000000")}
_Q2_PRIOR = {"1002": Decimal("80000")}

_Q2_FORMULAS = [
    "TB('1002','期末余额')",
    "TB('1002','期末余额')+TB('1012','期末余额')",
    "TB('1122','期末余额')-TB('1231','期末余额')",
    "SUM_TB('1400~1499','期末余额')",
    "ROW('BS-027')",
    "PREV('1002','期末余额')",
    "ABS(TB('1231','期末余额'))",
    "100+200*3",
    "",
]


def _fresh_ctx() -> FormulaContext:
    return FormulaContext.from_simple_map(
        dict(_Q2_TB), row_cache=dict(_Q2_ROWS), prior_map=dict(_Q2_PRIOR)
    )


class TestQ2Determinism:
    """属性 Q2：同输入同输出（纯函数，可缓存）。**Validates: Requirements 3.3**"""

    @given(formula=st.sampled_from(_Q2_FORMULAS))
    @settings(max_examples=15, deadline=None)
    def test_same_formula_same_ctx_same_result(self, formula):
        # 每次用结构相同但独立的 ctx 实例，验证结果只依赖输入值
        r1 = execute(formula, _fresh_ctx())
        r2 = execute(formula, _fresh_ctx())
        assert r1.value == r2.value
        assert r1.errors == r2.errors
        assert r1.warnings == r2.warnings
        assert r1.trace == r2.trace

    @given(formula=st.sampled_from(_Q2_FORMULAS))
    @settings(max_examples=15, deadline=None)
    def test_repeated_execution_is_stable(self, formula):
        ctx = _fresh_ctx()
        first = execute(formula, ctx).value
        # 多次对同一 ctx 求值结果稳定（execute 不应突变 ctx 造成漂移）
        for _ in range(3):
            assert execute(formula, ctx).value == first

    @given(
        a=st.integers(min_value=-1_000_000, max_value=1_000_000),
        b=st.integers(min_value=1, max_value=1_000_000),
    )
    @settings(max_examples=15, deadline=None)
    def test_arithmetic_determinism(self, a, b):
        """纯算术内核确定性 + Decimal（关联属性 Q2/Q3）。"""
        expr = f"TB('1002','期末余额')*{a}+{b}"
        ctx1 = FormulaContext.from_simple_map({"1002": Decimal("2")})
        ctx2 = FormulaContext.from_simple_map({"1002": Decimal("2")})
        v1 = execute(expr, ctx1).value
        v2 = execute(expr, ctx2).value
        assert v1 == v2
        assert isinstance(v1, Decimal)
