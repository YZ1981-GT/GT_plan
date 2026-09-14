# Feature: formula-management-library, Property 5: logic_check 与 reasonability 绝不改值
"""属性测试 P5：logic_check 与 reasonability 公式执行后**绝不修改任何数据单元值**。

*对任意* logic_check 或 reasonability 公式与任意数据状态（row_cache / tb_data），
执行该公式后所有数据单元的值与执行前逐一相等（仅产出 Issue_List / Hint_List，
从不修改任何值）。

被测：``app.services.formula_management.engine.execute_formula``（logic_check /
reasonability 分派分支）。以 ``resolve_refs=False`` 执行，聚焦引擎的非改值不变量
（引用解析 fail-open 已由 P8 覆盖）。生成器覆盖：

- 引用已存在 / 不存在的 row_cache 键（ROW）与 tb_data 科目（TB）；
- 可求值的算术 / 比较表达式，以及**无法求值**的畸形表达式（触发 logic_check 的
  「公式无法求值」项 / reasonability 的 WARNING 跳过分支）——两分支同样不得改值；
- target_cell 既可指向已有数据单元，也可指向新单元——无论如何都不得写入。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 6.3, 7.3**
"""

from __future__ import annotations

import asyncio
import copy
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import FormulaRecord, execute_formula


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助：execute_formula 为协程；resolve_refs=False 时无真实 async I/O。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到引擎输入空间（row_cache 键 / tb_data 科目 / 三类表达式）。
# ─────────────────────────────────────────────────────────────────────────────
_ROW_KEYS = st.text(alphabet="ABCDEFGHIJ0123456789-", min_size=1, max_size=6)
_ACCOUNT_CODES = st.text(alphabet="0123456789", min_size=3, max_size=4)
_DECIMALS = st.decimals(
    min_value=-1_000_000,
    max_value=1_000_000,
    allow_nan=False,
    allow_infinity=False,
    places=2,
)
# 明确畸形、无法求值的表达式，用于触发「无法求值」分支（仍不得改值）。
_MALFORMED = st.sampled_from(
    ["1 + * 2", "ROW(", ") (", "TB('x'", "* 3", "()", "1 + + 2"]
)


@st.composite
def _ctx_and_formula(draw):
    """联合抽取 FormulaContext（row_cache/tb_data）+ logic_check/reasonability 公式。

    表达式的原子从**当前上下文实际存在的键**与常量中抽取（智能生成器），并按一定
    概率引用不存在的键或注入畸形表达式，以覆盖可求值 / 不可求值两条分支。
    """
    keys = draw(st.lists(_ROW_KEYS, min_size=0, max_size=5, unique=True))
    codes = draw(st.lists(_ACCOUNT_CODES, min_size=0, max_size=5, unique=True))
    row_cache = {k: draw(_DECIMALS) for k in keys}
    tb_data = {c: {"期末余额": draw(_DECIMALS)} for c in codes}
    ctx = FormulaContext(row_cache=row_cache, tb_data=tb_data)

    # 原子表达式候选：常量 + 已有 ROW 引用 + 已有 TB 引用（也允许引用缺失键）。
    atom_options = [st.integers(min_value=0, max_value=10_000).map(str)]
    if keys:
        atom_options.append(st.sampled_from(keys).map(lambda k: f"ROW('{k}')"))
    if codes:
        atom_options.append(
            st.sampled_from(codes).map(lambda c: f"TB('{c}','期末余额')")
        )
    # 引用一个几乎必然缺失的键（求值为 0，仍属可求值路径）。
    atom_options.append(st.just("ROW('__missing__')"))
    atom = st.one_of(atom_options)

    n_terms = draw(st.integers(min_value=1, max_value=4))
    parts = [draw(atom)]
    for _ in range(n_terms - 1):
        parts.append(draw(st.sampled_from(["+", "-", "*", "/"])))
        parts.append(draw(atom))
    expr = " ".join(parts)

    # 约半数包成比较式（logic_check 条件 / reasonability 触发条件的典型形态）。
    if draw(st.booleans()):
        cmp = draw(st.sampled_from([">", "<", ">=", "<=", "==", "!="]))
        expr = f"{expr} {cmp} {draw(atom)}"

    # 约 1/4 概率替换为畸形表达式，覆盖「无法求值」分支。
    if draw(st.integers(min_value=0, max_value=3)) == 0:
        expr = draw(_MALFORMED)

    ftype = draw(st.sampled_from(["logic_check", "reasonability"]))

    # target_cell 可指向已有数据单元或新单元；两类型分支都不得写入它。
    target_choices = list(row_cache.keys()) + ["Z1", "NEW_CELL"]
    target_cell = draw(st.sampled_from(target_choices))

    formula = FormulaRecord(
        id="f-p5",
        formula_type=ftype,
        target_cell=target_cell,
        expression=expr,
        issue_description="P5 逻辑判断问题描述",
        hint_text="P5 合理性提示文案",
        addr_id=draw(st.sampled_from(["report/BS/1", None])),
    )
    return ctx, formula


@given(_ctx_and_formula())
@settings(max_examples=200)
def test_logic_check_reasonability_never_mutate_values(case):
    """P5：logic_check / reasonability 执行后所有数据单元值逐一不变。

    **Validates: Requirements 6.3, 7.3**
    """
    ctx, formula = case

    # 执行前的完整数据快照（深拷贝，隔离引用别名）。
    before_row_cache = copy.deepcopy(ctx.row_cache)
    before_tb_data = copy.deepcopy(ctx.tb_data)

    result = _run(
        execute_formula(None, formula=formula, ctx=ctx, resolve_refs=False)
    )

    # 核心不变量：数据单元逐一相等（键集合与每个值都不变）。
    assert ctx.row_cache == before_row_cache, "logic_check/reasonability 改动了 row_cache"
    assert ctx.tb_data == before_tb_data, "logic_check/reasonability 改动了 tb_data"

    # 语义辅证：这两类型绝不回填单元（updated_cells / values 恒为空）。
    assert result.updated_cells == []
    assert result.values == {}

    # target_cell 若原本存在于数据中，其值必须原样保留。
    if formula.target_cell in before_row_cache:
        assert ctx.row_cache[formula.target_cell] == before_row_cache[formula.target_cell]
