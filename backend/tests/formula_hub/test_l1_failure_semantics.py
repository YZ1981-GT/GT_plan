"""L1 失败语义、内置参数个数表、舍入、AST 预算（spec formula-hub-integrity-closure 任务 8；ADR-FHIC-01 / 02，D4）。

一、需求 2.3：除零、``ROW`` 缺行、未注册函数、参数个数不足（另查 ``IF`` 上限）、AST 超预算 ⇒ ``ok=False``、
   ``errors`` 含中文原因、``value`` 保持 ``Decimal('0')``（生产默认 ast 路径；正则降级路径同样 ``ok=False``）。
二、需求 2.6：``ROUND`` 统一 ``ROUND_HALF_UP``，L1 两条路径与 ``safe_eval_expr`` 同口径（``test_round_half_up``）。
三、``safe_eval_expr`` 同口径：除零 / 未注册函数 / 参数不足 / 语法错误抛 ``FormulaEvalError``（原先一律 0），``IF`` 只求选中分支。
四、需求 12.3 末句：AST 节点 > 2000 或深度 > 50 在求值前报错（边界 2000 / 50 正常）。
五、需求 2.9：参数个数表键集合 == ``BUILTIN_FUNCTION_NAMES`` ⊆ ``_REGISTRY``，注册自定义函数后
   ``_REGISTRY − 内置`` == 自定义函数集合（``test_arity_keys``）。
纯函数，不连库，生产函数不 mock。

**Validates: Requirements 2.3, 2.6, 2.9, 12.3**
"""
from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.services import formula_engine as fe
from app.services.formula_arity import (
    ARITY,
    BUILTIN_FUNCTION_NAMES,
    MAX_AST_DEPTH,
    MAX_AST_NODES,
    arity_problem,
)
from app.services.formula_engine import FormulaContext, FormulaEvalError, execute, safe_eval_expr

CJK = re.compile(r"[\u4e00-\u9fff]")


def _ctx() -> FormulaContext:
    return FormulaContext(
        tb_data={"1001": {"期末余额": Decimal("100")}, "1002": {"期末余额": Decimal("0")}},
        row_cache={"BS-001": Decimal("7")},
        prior_tb_data={"1001": {"期末余额": Decimal("50")}},
    )


@pytest.fixture(params=["ast", "regex"])
def parse_mode(request, monkeypatch):
    monkeypatch.setattr(fe, "_PARSE_MODE", request.param)
    return request.param


def _assert_failed(result, needle: str) -> None:
    assert not result.ok, result
    assert result.state in {"blocked", "error"}, result.state
    assert result.errors and all(CJK.search(e) for e in result.errors), result.errors
    assert any(needle in e for e in result.errors), (needle, result.errors)


# ── 一、失败语义 ────────────────────────────────────────────────────────────────────────

FAILURES = [  # (公式, ast 路径的原因片段, 正则降级路径的原因片段)
    ("1/0", "除数为 0", "除数为 0"),
    ("TB('1001','期末余额') / TB('1002','期末余额')", "除数为 0", "除数为 0"),
    ("TB('1001','期末余额') + 1/(2-2)", "除数为 0", "除数为 0"),
    ("ROW('BS-999')", "ROW('BS-999')", "ROW('BS-999')"),
    ("ROW('BS-001') + ROW('BS-999')", "ROW('BS-999')", "ROW('BS-999')"),
    ("EVIL(1)", "未注册函数", "未注册的函数：EVIL()"),
    ("IF(1, 2)", "IF() 参数个数不符", "IF() 参数个数不符"),
    ("IF(1, 2, 3, 4)", "IF() 参数个数不符", "IF() 参数个数不符"),
    ("MAX(1)", "MAX() 参数个数不符", "MAX() 参数个数不符"),
    ("MIN(1)", "MIN() 参数个数不符", "MIN() 参数个数不符"),
    ("ROUND()", "ROUND() 参数个数不符", "ROUND() 参数个数不符"),
    ("AUX('1001')", "AUX() 参数个数不符", "AUX()"),  # 正则路径不认单参 AUX，交 safe_eval_expr 判未注册
]


@pytest.mark.parametrize("formula, ast_needle, regex_needle", FAILURES, ids=[f[0] for f in FAILURES])
def test_failure_categories_are_not_ok(parse_mode, formula, ast_needle, regex_needle):
    result = execute(formula, _ctx())
    _assert_failed(result, ast_needle if parse_mode == "ast" else regex_needle)
    if parse_mode == "ast":
        assert result.value == Decimal("0") and isinstance(result.value, Decimal)


def test_failure_value_is_zero_not_partial_sum():
    """原先 ``TB + 1/(2-2)`` = 100（除零项按 0）、``ROW 存在 + ROW 缺行`` = 7：失败后不给部分和。"""
    for formula in ("TB('1001','期末余额') + 1/(2-2)", "ROW('BS-001') + ROW('BS-999')", "BS-001 + BS-999"):
        result = execute(formula, _ctx())
        assert (result.ok, result.value) == (False, Decimal("0")), (formula, result)


LOWER_BOUND_NAMES = sorted(name for name, (low, _high) in ARITY.items() if low >= 1)


@pytest.mark.parametrize("name", LOWER_BOUND_NAMES)
def test_every_builtin_below_lower_bound_is_error(name):
    low = ARITY[name][0]
    formula = f"{name}({', '.join(repr(str(i)) for i in range(low - 1))})"
    result = execute(formula, _ctx())
    _assert_failed(result, f"{name}() 参数个数不符")
    assert result.trace == [], "参数个数不足要在调用 handler 之前报错"


def test_unknown_function_kernel_and_blocked_entry():
    with pytest.raises(FormulaEvalError, match=r"未注册的函数：NOPE\(\)"):
        fe._eval_ast(fe.ASTFuncCall(name="NOPE", args=[]), _ctx(), [])
    result = execute("EVIL(1) + 1", _ctx())
    assert result.blocked and not result.ok and result.value == Decimal("0")


SUCCESSES = [  # 失败语义只收紧失败情形，正常写法值不变
    ("0/5", Decimal("0")),
    ("IF(1>0, 5, 1/0)", Decimal("5")),  # IF 只求被选中的分支
    ("IF(1<0, 1/0, 5)", Decimal("5")),
    ("ROW('BS-001') * 2", Decimal("14")),
    ("BS-001 + 1", Decimal("8")),
    ("ABS(-3, 9)", Decimal("3")),  # 求值期只查下限与 IF 上限；多给的参数由写入期 validator 拒
    ("MAX(1, 2, 3)", Decimal("3")),
    ("PREV(TB('1001','期末余额'))", Decimal("50")),  # PREV(TB(…)) 按内层两参计
    ("TB('1001')", Decimal("100")),
]


@pytest.mark.parametrize("formula, expected", SUCCESSES, ids=[s[0] for s in SUCCESSES])
def test_success_cases_unchanged(formula, expected):
    result = execute(formula, _ctx())
    assert (result.ok, result.value) == (True, expected), result


def test_arity_problem_write_time_checks_upper_bound():
    assert arity_problem("ABS", 2) is None
    assert arity_problem("ABS", 2, full=True) == "ABS() 参数个数不符：需要 1 个参数，实际 2 个"
    assert arity_problem("MAX", 1) == "MAX() 参数个数不符：至少需要 2 个参数，实际 1 个"
    assert arity_problem("AUX", 5, full=True) == "AUX() 参数个数不符：需要 2~4 个参数，实际 5 个"
    assert arity_problem("IF", 4) == "IF() 参数个数不符：需要 3 个参数，实际 4 个"
    assert arity_problem("NOT_BUILTIN", 0) is None


# ── 二、舍入 ────────────────────────────────────────────────────────────────────────────

ROUNDING = [
    ("ROUND(1.005, 2)", Decimal("1.01")),
    ("ROUND(-1.005, 2)", Decimal("-1.01")),
    ("ROUND(2.5, 0)", Decimal("3")),
    ("ROUND(-2.5, 0)", Decimal("-3")),
    ("ROUND(1.0049)", Decimal("1.00")),  # 缺位数按 2
    ("ROUND(1250, -2)", Decimal("1300")),
]


@pytest.mark.parametrize("formula, expected", ROUNDING, ids=[r[0] for r in ROUNDING])
def test_round_half_up(formula, expected, monkeypatch):
    seen = {}
    for mode in ("ast", "regex"):
        monkeypatch.setattr(fe, "_PARSE_MODE", mode)
        result = execute(formula, FormulaContext())
        assert result.ok, (mode, result)
        seen[mode] = result.value
    seen["safe_eval_expr"] = safe_eval_expr(formula)
    assert seen == dict.fromkeys(seen, expected), seen


# ── 三、safe_eval_expr 同口径 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr, needle", [
    ("10 / 0", "除数为 0"),
    ("10 / (3 - 3)", "除数为 0"),
    ("EVIL(1)", "未注册的函数：EVIL()"),
    ("__import__('os')", "未注册的函数：__import__()"),
    ("os.system('x')", "不支持的写法"),
    ("IF(1, 2)", "IF() 参数个数不符"),
    ("MAX(1)", "MAX() 参数个数不符"),
    ("ROUND()", "ROUND() 参数个数不符"),
    ("1 +", "语法错误"),
    ("2 ** 3", "不支持运算符"),
])
def test_safe_eval_expr_raises_instead_of_zero(expr, needle):
    with pytest.raises(FormulaEvalError) as info:
        safe_eval_expr(expr)
    assert needle in str(info.value), str(info.value)


def test_safe_eval_expr_success_paths():
    assert safe_eval_expr("") == Decimal("0") == safe_eval_expr("   ")
    assert safe_eval_expr("IF(1, 5, 1/0)") == Decimal("5")
    assert safe_eval_expr("(10 - 4) / 2 + ABS(-1)") == Decimal("4")
    assert safe_eval_expr("MAX(3, 9, 4) - MIN(3, 9)") == Decimal("6")


# ── 四、AST 预算 ──────────────────────────────────────────────────────────────────────────

def _nested(depth: int, leaf: str = "1") -> str:
    """``ABS(ABS(…leaf…))``：AST 深度 = depth（depth - 1 层调用 + 叶）。"""
    return "ABS(" * (depth - 1) + leaf + ")" * (depth - 1)


def _wide(args: int, first: str = "1") -> str:
    """``MAX(first,1,1,…)``：节点数 = args + 1，深度 2。"""
    return "MAX(" + ",".join([first] + ["1"] * (args - 1)) + ")"


@pytest.mark.parametrize("formula, ok", [
    (_nested(MAX_AST_DEPTH), True),
    (_nested(MAX_AST_DEPTH + 1), False),
    ("+".join(["1"] * MAX_AST_DEPTH), True),  # 左结合链：深度 = 项数
    ("+".join(["1"] * (MAX_AST_DEPTH + 1)), False),
    (_wide(MAX_AST_NODES - 1), True),
    (_wide(MAX_AST_NODES), False),
], ids=["depth50", "depth51", "chain50", "chain51", "nodes2000", "nodes2001"])
def test_ast_budget_boundaries(formula, ok):
    result = execute(formula, _ctx())
    assert result.ok is ok, result.errors
    if not ok:
        assert result.errors == [result.errors[0]] and "表达式超出求值预算" in result.errors[0], result.errors


@pytest.mark.parametrize("formula", [_nested(MAX_AST_DEPTH + 1, "ROW('BS-999')"), _wide(MAX_AST_NODES, "ROW('BS-999')")],
                         ids=["deep", "wide"])
def test_ast_budget_checked_before_evaluation(formula):
    """超预算的公式里有缺行引用：只报预算、trace 为空 ⇒ 求值根本没开始。"""
    result = execute(formula, _ctx())
    assert len(result.errors) == 1 and "表达式超出求值预算" in result.errors[0], result.errors
    assert result.trace == [] and result.value == Decimal("0")


@pytest.mark.parametrize("expr", [_wide(MAX_AST_NODES), _nested(MAX_AST_DEPTH + 1)], ids=["wide", "deep"])
def test_safe_eval_expr_has_the_same_budget(expr):
    with pytest.raises(FormulaEvalError, match="表达式超出求值预算"):
        safe_eval_expr(expr)


# ── 五、参数个数表只管内置函数 ──────────────────────────────────────────────────────────────

def test_arity_keys():
    engine = fe.FormulaEngine()
    name = "FHIC_T8_CUSTOM"
    engine.register_custom_function(name, description="任务 8 守卫用", expression="1+1")
    try:
        registry = fe._REGISTRY.known_function_names()
        custom = {m["name"] for m in fe._REGISTRY.list_all() if m.get("category") == "自定义"}
        assert set(ARITY) == BUILTIN_FUNCTION_NAMES
        assert BUILTIN_FUNCTION_NAMES <= registry
        assert name in custom and registry - BUILTIN_FUNCTION_NAMES == custom
        assert name not in ARITY and arity_problem(name, 9) is None
        result = execute(f"{name}()", FormulaContext())  # 自定义函数不受内置参数表约束
        assert (result.ok, result.value) == (True, Decimal("2")), result
    finally:
        engine.unregister_custom_function(name)
    assert name not in fe._REGISTRY.known_function_names()
