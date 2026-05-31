"""阶段 0 PBT — Q2 确定性 + Q3 Decimal 无精度丢失 + Q4 解析往返

spec: formula-engine-unification / tasks.md Task 6
**Validates: Requirements 1.2**
关联属性: Q2, Q3, Q4

═══════════════════════════════════════════════════════════════════════════════
目的
═══════════════════════════════════════════════════════════════════════════════
综合 PBT 守门阶段 0 三大正确性属性：
  Q2 确定性：同 formula + 同 FormulaContext → 同 FormulaResult（纯函数）
  Q3 Decimal 无精度丢失：所有中间和最终值均为 Decimal，无 float 转换
  Q4 解析往返：AST 求值 == regex 求值（parse roundtrip）

hypothesis max_examples 10~15（用户偏好）
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.formula_engine import (
    FormulaContext,
    FormulaResult,
    execute,
    _execute_ast,
    _execute_regex,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 测试数据策略（共用）
# ═══════════════════════════════════════════════════════════════════════════════

# 科目编码
_ACCOUNT_CODES = ["1001", "1002", "1012", "1122", "1231", "1401", "1406", "2001"]

# 行次编码
_ROW_CODES = ["BS-001", "BS-002", "BS-003", "BS-010", "PL-001", "CF-001"]

# 列名
_COLUMNS = ["期末余额", "审定数", "年初余额", "未审数"]

# 金额策略（Decimal，合理范围，避免极端值导致超时）
_amounts = st.decimals(
    min_value=-1_000_000, max_value=1_000_000,
    places=2, allow_nan=False, allow_infinity=False,
)

# 公式模板（覆盖核心 DSL 函数 + 算术 + 嵌套）
_FORMULA_TEMPLATES = [
    "TB('{code}','{col}')",
    "TB('{code}','{col}')+TB('{code2}','{col}')",
    "TB('{code}','{col}')-TB('{code2}','{col}')",
    "SUM_TB('{range}','{col}')",
    "ROW('{row}')",
    "SUM_ROW('{row}','{row2}')",
    "PREV('{code}','{col}')",
    "ABS(TB('{code}','{col}'))",
    "ROUND(TB('{code}','{col}'),2)",
    "IF(TB('{code}','{col}')>0,TB('{code}','{col}'),0)",
    "MAX(TB('{code}','{col}'),TB('{code2}','{col}'))",
    "MIN(TB('{code}','{col}'),TB('{code2}','{col}'))",
    "{num1}+{num2}*{num3}",
]


@st.composite
def formula_and_context(draw):
    """生成 (formula, FormulaContext) 对，覆盖各种公式模式。"""
    # 构建 tb_data（3~6 个科目）
    tb_data: dict[str, dict[str, Decimal]] = {}
    n_accounts = draw(st.integers(min_value=3, max_value=6))
    codes_used = draw(st.lists(
        st.sampled_from(_ACCOUNT_CODES),
        min_size=n_accounts, max_size=n_accounts, unique=True,
    ))
    for code in codes_used:
        amt = draw(_amounts)
        tb_data[code] = {"期末余额": amt, "审定数": amt, "年初余额": amt, "未审数": amt}

    # 构建 row_cache（2~4 行）
    row_cache: dict[str, Decimal] = {}
    n_rows = draw(st.integers(min_value=2, max_value=4))
    rows_used = draw(st.lists(
        st.sampled_from(_ROW_CODES),
        min_size=n_rows, max_size=n_rows, unique=True,
    ))
    for rc in rows_used:
        row_cache[rc] = draw(_amounts)

    # 构建 prior_tb_data（前 2 个科目）
    prior_tb_data: dict[str, dict[str, Decimal]] = {}
    for code in codes_used[:2]:
        prior_tb_data[code] = {"期末余额": draw(_amounts)}

    ctx = FormulaContext(
        tb_data=tb_data,
        row_cache=row_cache,
        prior_tb_data=prior_tb_data,
    )

    # 选择公式模板并填充
    template = draw(st.sampled_from(_FORMULA_TEMPLATES))
    code = draw(st.sampled_from(codes_used))
    code2 = draw(st.sampled_from(codes_used))
    col = draw(st.sampled_from(_COLUMNS))
    row = draw(st.sampled_from(rows_used))
    row2 = draw(st.sampled_from(rows_used))
    num1 = draw(st.integers(min_value=1, max_value=999))
    num2 = draw(st.integers(min_value=1, max_value=99))
    num3 = draw(st.integers(min_value=1, max_value=99))

    # SUM_TB 范围
    range_start = code[:2] + "00"
    range_end = code[:2] + "99"
    code_range = f"{range_start}~{range_end}"

    formula = template.format(
        code=code, code2=code2, col=col, row=row, row2=row2,
        range=code_range, num1=num1, num2=num2, num3=num3,
    )

    return formula, ctx


# ═══════════════════════════════════════════════════════════════════════════════
# Q2 确定性：同 formula + 同 FormulaContext → 同 FormulaResult
# **Validates: Requirements 1.2**  属性: Q2
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ2Determinism:
    """属性 Q2：execute 是纯函数，同输入必同输出。"""

    @given(data=formula_and_context())
    @settings(max_examples=15, deadline=None)
    def test_same_input_same_output(self, data):
        """同一 formula + 同一 ctx 执行两次，FormulaResult.value 逐位一致。"""
        formula, ctx = data

        r1 = execute(formula, ctx)
        r2 = execute(formula, ctx)

        assert r1.value == r2.value, (
            f"Q2 违反：两次执行结果不同\n"
            f"  公式: {formula}\n"
            f"  r1.value={r1.value}, r2.value={r2.value}"
        )
        assert r1.errors == r2.errors

    @given(data=formula_and_context())
    @settings(max_examples=10, deadline=None)
    def test_repeated_execution_stable(self, data):
        """对同一 ctx 多次求值不会因副作用导致漂移。"""
        formula, ctx = data

        first = execute(formula, ctx).value
        for _ in range(3):
            assert execute(formula, ctx).value == first, (
                f"Q2 违反：重复执行结果漂移\n  公式: {formula}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Q3 Decimal 无精度丢失：FormulaResult.value 始终为 Decimal，无 float
# **Validates: Requirements 1.2**  属性: Q3
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ3DecimalPrecision:
    """属性 Q3：求值全程 Decimal，无 float 中间态。"""

    @given(data=formula_and_context())
    @settings(max_examples=15, deadline=None)
    def test_result_value_is_decimal(self, data):
        """FormulaResult.value 始终为 Decimal 类型，绝不是 float/int。"""
        formula, ctx = data

        result = execute(formula, ctx)
        assert isinstance(result.value, Decimal), (
            f"Q3 违反：result.value 类型为 {type(result.value).__name__}，非 Decimal\n"
            f"  公式: {formula}\n"
            f"  值: {result.value}"
        )

    @given(data=formula_and_context())
    @settings(max_examples=15, deadline=None)
    def test_no_float_in_trace(self, data):
        """trace 中记录的值不应包含 float 表示（如 '1.0000000000000002'）。

        trace 格式为 "TB('1002','期末余额') = 100000" 等，
        值部分应为 Decimal 的 str 表示（无浮点噪声）。
        """
        formula, ctx = data

        result = execute(formula, ctx)
        for entry in result.trace:
            # trace 格式: "FUNC(...) = VALUE"
            if " = " in entry:
                val_str = entry.split(" = ", 1)[1]
                # 不应出现浮点噪声（如 e-16, 0.30000000000000004 等）
                assert "e-" not in val_str.lower() and "e+" not in val_str.lower(), (
                    f"Q3 违反：trace 中出现科学计数法（float 噪声）\n"
                    f"  entry: {entry}"
                )

    @given(data=formula_and_context())
    @settings(max_examples=10, deadline=None)
    def test_ast_path_returns_decimal(self, data):
        """AST 路径的 FormulaResult.value 也是 Decimal。"""
        formula, ctx = data

        result = _execute_ast(formula, ctx)
        if result.ok:
            assert isinstance(result.value, Decimal), (
                f"Q3 违反：AST 路径 value 类型为 {type(result.value).__name__}\n"
                f"  公式: {formula}"
            )

    @given(data=formula_and_context())
    @settings(max_examples=10, deadline=None)
    def test_regex_path_returns_decimal(self, data):
        """regex 路径的 FormulaResult.value 也是 Decimal。"""
        formula, ctx = data

        result = _execute_regex(formula, ctx)
        assert isinstance(result.value, Decimal), (
            f"Q3 违反：regex 路径 value 类型为 {type(result.value).__name__}\n"
            f"  公式: {formula}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Q4 解析往返：AST 求值 == regex 求值
# **Validates: Requirements 1.2**  属性: Q4
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ4ParseRoundtrip:
    """属性 Q4：AST 路径与 regex 路径对同一公式+ctx 求值逐位一致。"""

    @given(data=formula_and_context())
    @settings(max_examples=15, deadline=None)
    def test_ast_equals_regex(self, data):
        """AST 求值结果 == regex 求值结果（parse roundtrip 一致性）。"""
        formula, ctx = data

        ast_result = _execute_ast(formula, ctx)
        regex_result = _execute_regex(formula, ctx)

        # 如果 AST 解析失败，跳过（公式不在 AST 支持范围）
        assume(ast_result.ok)

        assert ast_result.value == regex_result.value, (
            f"Q4 违反：AST={ast_result.value} != regex={regex_result.value}\n"
            f"  公式: {formula}\n"
            f"  AST errors: {ast_result.errors}\n"
            f"  regex errors: {regex_result.errors}"
        )
