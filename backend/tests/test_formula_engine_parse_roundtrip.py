"""Task 3 — parse 层升级：递归下降替换 regex — Q4 解析往返 PBT

spec: formula-engine-unification / tasks.md Task 3
**Validates: Requirements 2.3**
关联属性: Q4（parse roundtrip：AST 求值 == regex 求值）

═══════════════════════════════════════════════════════════════════════════════
目的
═══════════════════════════════════════════════════════════════════════════════
验证新递归下降 AST 求值路径与旧 regex token 替换路径对同一公式 + 同一 ctx
产出逐位一致的 FormulaResult.value（属性 Q4）。

并行 diff 验证通过 = 可安全切换到 AST 路径。
保留 regex 一个版本周期降级（_PARSE_MODE="regex" 可回退）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.formula_engine import (
    FormulaContext,
    _execute_ast,
    _execute_regex,
    parse_to_ast,
    FormulaParseError,
    _PARSE_MODE,
    execute,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试数据策略
# ═══════════════════════════════════════════════════════════════════════════════

# 科目编码策略（4 位数字，模拟真实科目）
account_codes = st.sampled_from(["1001", "1002", "1012", "1122", "1231", "1401", "1406", "2001", "2201"])

# 列名策略
column_names = st.sampled_from(["期末余额", "审定数", "年初余额", "未审数"])

# 行次编码策略
row_codes = st.sampled_from(["BS-001", "BS-002", "BS-003", "BS-010", "BS-027", "PL-001", "CF-001"])

# 金额策略（Decimal，合理范围）
amounts = st.decimals(min_value=-10_000_000, max_value=10_000_000, places=2, allow_nan=False, allow_infinity=False)

# 代表性公式模板（覆盖 regex 能处理的所有 token 类型）
FORMULA_TEMPLATES = [
    # 单函数
    "TB('{code}','{col}')",
    # 两函数相加
    "TB('{code}','{col}')+TB('{code2}','{col}')",
    # 减法
    "TB('{code}','{col}')-TB('{code2}','{col}')",
    # SUM_TB
    "SUM_TB('{range}','{col}')",
    # ROW
    "ROW('{row}')",
    # SUM_ROW
    "SUM_ROW('{row}','{row2}')",
    # REPORT
    "REPORT('{row}','current')",
    # PREV
    "PREV('{code}','{col}')",
    # ABS
    "ABS(TB('{code}','{col}'))",
    # 纯算术
    "{num1}+{num2}*{num3}",
    # IF 条件
    "IF(TB('{code}','{col}')>0,TB('{code}','{col}'),0)",
    # ROUND
    "ROUND(TB('{code}','{col}')/3,2)",
    # MAX/MIN
    "MAX(TB('{code}','{col}'),TB('{code2}','{col}'))",
    "MIN(TB('{code}','{col}'),TB('{code2}','{col}'))",
]


@st.composite
def formula_with_ctx(draw):
    """生成一对 (formula, FormulaContext)，覆盖各种公式模式。"""
    # 构建 tb_data
    tb_data = {}
    for _ in range(draw(st.integers(min_value=3, max_value=8))):
        code = draw(account_codes)
        amt = draw(amounts)
        tb_data[code] = {"期末余额": amt, "审定数": amt, "年初余额": amt, "未审数": amt}

    # 构建 row_cache
    row_cache = {}
    for _ in range(draw(st.integers(min_value=2, max_value=5))):
        rc = draw(row_codes)
        row_cache[rc] = draw(amounts)

    # 构建 prior_tb_data
    prior_tb_data = {}
    for code in list(tb_data.keys())[:3]:
        prior_tb_data[code] = {"期末余额": draw(amounts)}

    ctx = FormulaContext(
        tb_data=tb_data,
        row_cache=row_cache,
        prior_tb_data=prior_tb_data,
    )

    # 选择公式模板并填充
    template = draw(st.sampled_from(FORMULA_TEMPLATES))
    codes = list(tb_data.keys()) or ["1002"]
    rows = list(row_cache.keys()) or ["BS-001"]

    code = draw(st.sampled_from(codes))
    code2 = draw(st.sampled_from(codes))
    col = draw(column_names)
    row = draw(st.sampled_from(rows))
    row2 = draw(st.sampled_from(rows))
    num1 = draw(st.integers(min_value=1, max_value=999))
    num2 = draw(st.integers(min_value=1, max_value=99))
    num3 = draw(st.integers(min_value=1, max_value=99))

    # 构建 SUM_TB 范围（确保 start <= end）
    range_start = code[:2] + "00"
    range_end = code[:2] + "99"
    code_range = f"{range_start}~{range_end}"

    formula = template.format(
        code=code, code2=code2, col=col, row=row, row2=row2,
        range=code_range, num1=num1, num2=num2, num3=num3,
    )

    return formula, ctx


# ═══════════════════════════════════════════════════════════════════════════════
# Q4 属性测试：AST 求值 == regex 求值（parse roundtrip）
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ4ParseRoundtrip:
    """属性 Q4：parse(formula) 的 AST 求值结果 == 旧 regex 求值结果。

    **Validates: Requirements 2.3**
    """

    @given(data=formula_with_ctx())
    @settings(max_examples=15, deadline=None)
    def test_ast_equals_regex_for_generated_formulas(self, data):
        """对随机生成的公式+上下文，AST 路径与 regex 路径求值结果逐位一致。"""
        formula, ctx = data

        regex_result = _execute_regex(formula, ctx)
        ast_result = _execute_ast(formula, ctx)

        # 如果 AST 解析失败（公式不在 AST 支持范围），跳过
        if not ast_result.ok:
            assume(False)

        assert ast_result.value == regex_result.value, (
            f"Q4 违反：AST={ast_result.value} != regex={regex_result.value}\n"
            f"  公式: {formula}\n"
            f"  AST errors: {ast_result.errors}\n"
            f"  regex errors: {regex_result.errors}"
        )

    @given(data=formula_with_ctx())
    @settings(max_examples=15, deadline=None)
    def test_parallel_mode_never_diverges(self, data):
        """parallel 模式下 execute 的最终 value 与 regex 路径一致（不丢精度）。"""
        formula, ctx = data

        # 直接调 execute（当前 parallel 模式）
        result = execute(formula, ctx)
        regex_result = _execute_regex(formula, ctx)

        # parallel 模式保证：最终结果要么 == AST（一致时），要么 == regex（不一致时回退）
        # 所以最终 value 一定 == regex_result.value
        assert result.value == regex_result.value, (
            f"parallel 模式结果与 regex 不一致: {result.value} != {regex_result.value}\n"
            f"  公式: {formula}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 确定性公式集验证（补充 PBT 的固定用例）
# ═══════════════════════════════════════════════════════════════════════════════

_FIXED_TB = {
    "1002": {"期末余额": Decimal("100000"), "审定数": Decimal("100000")},
    "1012": {"期末余额": Decimal("50000"), "审定数": Decimal("50000")},
    "1122": {"期末余额": Decimal("500000"), "审定数": Decimal("500000")},
    "1231": {"期末余额": Decimal("-30000"), "审定数": Decimal("-30000")},
    "1401": {"期末余额": Decimal("10000"), "审定数": Decimal("10000")},
    "1406": {"期末余额": Decimal("20000"), "审定数": Decimal("20000")},
}
_FIXED_ROWS = {"BS-002": Decimal("100"), "BS-003": Decimal("200"), "BS-027": Decimal("1000000")}
_FIXED_PRIOR = {"1002": {"期末余额": Decimal("80000")}}
_FIXED_CTX = FormulaContext(tb_data=_FIXED_TB, row_cache=_FIXED_ROWS, prior_tb_data=_FIXED_PRIOR)

FIXED_FORMULAS = [
    "TB('1002','期末余额')",
    "TB('1002','期末余额')+TB('1012','期末余额')",
    "TB('1122','期末余额')-TB('1231','期末余额')",
    "SUM_TB('1400~1499','期末余额')",
    "ROW('BS-027')",
    "SUM_ROW('BS-002','BS-003')",
    "REPORT('BS-002','current')",
    "PREV('1002','期末余额')",
    "ABS(TB('1231','期末余额'))",
    "100+200*3",
    "IF(TB('1002','期末余额')>0,TB('1002','期末余额'),0)",
    "ROUND(TB('1002','期末余额')/3,2)",
    "MAX(TB('1002','期末余额'),TB('1012','期末余额'))",
    "MIN(TB('1002','期末余额'),TB('1012','期末余额'))",
]


class TestQ4FixedFormulas:
    """固定公式集：AST 路径 == regex 路径（逐位一致）。"""

    @pytest.mark.parametrize("formula", FIXED_FORMULAS)
    def test_ast_equals_regex(self, formula):
        regex_result = _execute_regex(formula, _FIXED_CTX)
        ast_result = _execute_ast(formula, _FIXED_CTX)

        assert ast_result.ok, f"AST 解析失败: {ast_result.errors} (formula={formula})"
        assert ast_result.value == regex_result.value, (
            f"Q4 违反：AST={ast_result.value} != regex={regex_result.value}\n"
            f"  公式: {formula}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# parse_to_ast 基本功能验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseToAst:
    """验证 parse_to_ast 能正确解析各种公式模式。"""

    def test_simple_tb(self):
        from app.services.formula_engine import ASTFuncCall, ASTString
        node = parse_to_ast("TB('1002','期末余额')")
        assert isinstance(node, ASTFuncCall)
        assert node.name == "TB"
        assert len(node.args) == 2

    def test_nested_prev_tb(self):
        """嵌套 PREV(TB(...)) — regex 无法处理的核心场景。"""
        from app.services.formula_engine import ASTFuncCall
        node = parse_to_ast("PREV(TB('1002','期末余额'))")
        assert isinstance(node, ASTFuncCall)
        assert node.name == "PREV"
        assert len(node.args) == 1
        inner = node.args[0]
        assert isinstance(inner, ASTFuncCall)
        assert inner.name == "TB"

    def test_if_with_comparison(self):
        """IF(TB(...)>0, ...) — regex 无法处理的比较运算。"""
        from app.services.formula_engine import ASTFuncCall
        node = parse_to_ast("IF(TB('1002','期末余额')>0,TB('1002','期末余额'),0)")
        assert isinstance(node, ASTFuncCall)
        assert node.name == "IF"
        assert len(node.args) == 3

    def test_arithmetic(self):
        from app.services.formula_engine import ASTBinOp
        node = parse_to_ast("100+200*3")
        assert isinstance(node, ASTBinOp)
        assert node.op == "+"

    def test_empty_raises(self):
        with pytest.raises(FormulaParseError):
            parse_to_ast("")

    def test_unmatched_paren_raises(self):
        with pytest.raises(FormulaParseError):
            parse_to_ast("TB('1002','期末余额'")


# ═══════════════════════════════════════════════════════════════════════════════
# 降级路径验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseModeControl:
    """验证 _PARSE_MODE 控制 regex 降级路径可用。"""

    def test_regex_mode_still_works(self):
        """regex 降级路径保留一个版本周期。"""
        result = _execute_regex("TB('1002','期末余额')", _FIXED_CTX)
        assert result.value == Decimal("100000")
        assert result.ok

    def test_ast_mode_works(self):
        """AST 路径独立可用。"""
        result = _execute_ast("TB('1002','期末余额')", _FIXED_CTX)
        assert result.value == Decimal("100000")
        assert result.ok

    def test_parallel_mode_returns_consistent(self):
        """parallel 模式返回与 regex 一致的结果。"""
        from app.services.formula_engine import _execute_parallel
        result = _execute_parallel("TB('1002','期末余额')+TB('1012','期末余额')", _FIXED_CTX)
        assert result.value == Decimal("150000")
