"""公式四态分类测试（P0-项2 · spec d4-dual-mode-formula-governance）

验证 app.services.formula_management.formula_state.classify_formula 与引擎 blocked 标记：
  - 四态 ok/missing/damaged/blocked 互斥、不混淆。
  - eval/exec/URL/未注册函数 → blocked（不静默返 0 冒充 ok）。
  - 合法公式 → ok；key 不存在 → missing；坏 AST → damaged。
  - 引擎 execute：blocked 公式 ok=False 且 state='blocked'（value 仍给但不冒充正常）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.formula_engine import FormulaContext, execute
from app.services.formula_management.formula_state import (
    FormulaState,
    classify_formula,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 单元：四态
# ═══════════════════════════════════════════════════════════════════════════════


def test_ok_valid_formula():
    assert classify_formula("TB('1001','期末余额')+ROW('BS-002')") == FormulaState.OK


def test_ok_empty_expression_when_key_exists():
    assert classify_formula("", key_exists=True) == FormulaState.OK
    assert classify_formula(None, key_exists=True) == FormulaState.OK


def test_missing_when_key_absent():
    # key 不存在优先判 missing（即便表达式本身合法）
    assert classify_formula("TB('1001','期末余额')", key_exists=False) == FormulaState.MISSING
    assert classify_formula(None, key_exists=False) == FormulaState.MISSING


@pytest.mark.parametrize("expr", ["TB('1001'", "TB('1001','x'))", "IF(TB('1001')>", "(("])
def test_damaged_bad_ast(expr):
    assert classify_formula(expr) == FormulaState.DAMAGED


@pytest.mark.parametrize(
    "expr",
    [
        "eval('1+1')",
        "exec('x=1')",
        "__import__('os')",
        "HACKFUNC('x')",              # 未注册函数
        "WP('http://evil.com','B5')",  # URL 外链
        "WP('file:///etc/passwd','B5')",
        "getattr(x,'y')",
    ],
)
def test_blocked_non_whitelist_or_dangerous(expr):
    assert classify_formula(expr) == FormulaState.BLOCKED


# ═══════════════════════════════════════════════════════════════════════════════
# 引擎 execute：blocked 不静默返 0 冒充正常
# ═══════════════════════════════════════════════════════════════════════════════


def test_engine_blocks_unknown_function():
    r = execute("NONEXIST('x')", FormulaContext())
    assert r.blocked is True and r.ok is False and r.state == "blocked"


def test_engine_blocks_eval():
    r = execute("eval('2+2')", FormulaContext())
    assert r.blocked is True and r.ok is False


def test_engine_ok_for_valid():
    r = execute("TB('1002','期末余额')", FormulaContext.from_simple_map({"1002": Decimal("5")}))
    assert r.blocked is False and r.ok is True and r.state == "ok"


def test_engine_damaged_for_bad_ast():
    r = execute("TB('1002'", FormulaContext())
    assert r.ok is False and r.state == "damaged" and r.blocked is False


# ═══════════════════════════════════════════════════════════════════════════════
# PBT（max_examples=5）：四态互不混淆
# ═══════════════════════════════════════════════════════════════════════════════

# 明确各态的生成器（互斥输入空间，用 assume 去交叠）
_ok_st = st.sampled_from([
    "TB('1001','期末余额')",
    "ROW('BS-002')",
    "SUM_TB('1001~1099','期末余额')",
    "ABS(TB('1001','期末余额'))",
    "IF(ROW('X')>0,1,0)",
])
_blocked_st = st.sampled_from([
    "eval('1')",
    "exec('a=1')",
    "HACK('x')",
    "UNKNOWNFN('y')",
    "WP('https://evil.example','B5')",
    "__import__('os')",
])
_damaged_st = st.sampled_from([
    "TB('1001'",
    "((",
    "IF(TB('1001')>",
    "SUM_TB('a~b'",
])


@settings(max_examples=5)
@given(expr=_ok_st)
def test_property_ok_class(expr):
    """**Validates: P0-项2** 合法白名单公式 → ok（key 存在时）。"""
    assert classify_formula(expr, key_exists=True) == FormulaState.OK


@settings(max_examples=5)
@given(expr=_blocked_st)
def test_property_blocked_class(expr):
    """**Validates: P0-项2** eval/exec/URL/未注册函数 → blocked，绝不判成 ok/missing/damaged。"""
    st_ = classify_formula(expr, key_exists=True)
    assert st_ == FormulaState.BLOCKED
    assert st_ not in (FormulaState.OK, FormulaState.MISSING, FormulaState.DAMAGED)


@settings(max_examples=5)
@given(expr=_damaged_st)
def test_property_damaged_class(expr):
    """**Validates: P0-项2** 坏 AST → damaged（非 blocked/ok）。"""
    # damaged 生成器不含危险标识/未注册函数调用，确保与 blocked 不交叠
    assume("eval" not in expr.lower() and "://" not in expr)
    st_ = classify_formula(expr, key_exists=True)
    assert st_ == FormulaState.DAMAGED


@settings(max_examples=5)
@given(expr=st.one_of(_ok_st, _blocked_st, _damaged_st))
def test_property_missing_overrides_when_key_absent(expr):
    """**Validates: P0-项2** key 不存在 → missing（优先于表达式态，四态互斥）。"""
    assert classify_formula(expr, key_exists=False) == FormulaState.MISSING
