# Feature: formula-management-library, Property 9: auto_calc 成功执行记录最近计算时间
"""属性测试 P9：auto_calc 成功执行记录最近计算时间（Task 2.8）。

**Property 9: auto_calc 成功执行记录最近计算时间**

被测：``app.services.formula_management.engine.execute_formula`` 的 auto_calc 分派分支
（``_exec_auto_calc``，design §Components 2 / Data Models §5）。auto_calc 公式**成功
求值并回填目标单元**后，``FormulaExecResult.last_computed_at`` 必须从 ``None``/旧值被
更新为**本次执行时刻**（一个 UTC 时区感知时间戳，落在执行前后瞬间之间）；反之，公式
**无法求值**（保留目标单元原值、不回填）时，``last_computed_at`` 必须保持 ``None``——
即绝不为一次失败的求值写入时间戳（Req 5.5）。

Req 13.3 / 15.3 / 16.4 / 17.5 分别覆盖审定表回写 / 报表增量重算 / 报表生成 / 附注执行
场景下「auto_calc 单元记 last_computed_at」的同一契约——底层均落在 ``execute_formula``
的 auto_calc 分支时间戳语义。本属性以 Hypothesis 随机可求值 auto_calc 公式 + 随机
``FormulaContext`` 验证成功分支，并以随机畸形表达式验证失败分支不写时间戳。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 5.4, 13.3, 15.3, 16.4, 17.5**
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
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
# 智能生成器：约束到引擎输入空间（row_cache 键 / tb_data 科目）。
# 目标单元一律取新单元，避免与四表库叶子源只读守卫（is_four_table_target）冲突。
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
# 明确畸形、无法求值的表达式（L1 内核解析失败 → fr.ok == False）。
_MALFORMED = st.sampled_from(
    ["1 + * 2", "ROW(", ") (", "TB('x'", "* 3", "()", "1 + + 2"]
)


@st.composite
def _ctx_and_context(draw):
    """联合抽取 FormulaContext（row_cache/tb_data）与可用于构造表达式的原子候选。

    返回 ``(ctx, atom_strategy)``；atom 从**上下文实际存在的键**与常量中抽取，保证
    可求值分支确实能被 L1 内核成功求值。
    """
    keys = draw(st.lists(_ROW_KEYS, min_size=0, max_size=5, unique=True))
    codes = draw(st.lists(_ACCOUNT_CODES, min_size=0, max_size=5, unique=True))
    row_cache = {k: draw(_DECIMALS) for k in keys}
    tb_data = {c: {"期末余额": draw(_DECIMALS)} for c in codes}
    ctx = FormulaContext(row_cache=row_cache, tb_data=tb_data)

    atom_options = [st.integers(min_value=0, max_value=10_000).map(str)]
    if keys:
        atom_options.append(st.sampled_from(keys).map(lambda k: f"ROW('{k}')"))
    if codes:
        atom_options.append(
            st.sampled_from(codes).map(lambda c: f"TB('{c}','期末余额')")
        )
    # 缺失键求值为 0，仍属可求值路径。
    atom_options.append(st.just("ROW('__missing__')"))
    return ctx, st.one_of(atom_options)


@st.composite
def _evaluatable_auto_calc(draw):
    """随机**可求值** auto_calc 公式 + 随机 FormulaContext。

    仅用 ``+ - *`` 组合原子，规避除零等运行期失败，确保求值成功分支。目标单元取
    新单元（非四表库、非已有键），保证回填生效。
    """
    ctx, atom = draw(_ctx_and_context())
    n_terms = draw(st.integers(min_value=1, max_value=4))
    parts = [draw(atom)]
    for _ in range(n_terms - 1):
        parts.append(draw(st.sampled_from(["+", "-", "*"])))
        parts.append(draw(atom))
    expr = " ".join(parts)

    formula = FormulaRecord(
        id="f-p9-ok",
        formula_type="auto_calc",
        target_cell="RESULT_CELL",  # 新单元，非四表库叶子
        expression=expr,
    )
    return ctx, formula


@st.composite
def _unevaluatable_auto_calc(draw):
    """随机**无法求值** auto_calc 公式 + 随机 FormulaContext（畸形表达式）。"""
    ctx, _atom = draw(_ctx_and_context())
    formula = FormulaRecord(
        id="f-p9-bad",
        formula_type="auto_calc",
        target_cell="RESULT_CELL",
        expression=draw(_MALFORMED),
    )
    return ctx, formula


@given(_evaluatable_auto_calc())
@settings(max_examples=200)
def test_auto_calc_success_records_execution_moment(case):
    """P9 成功分支：成功求值后 last_computed_at 更新为本次执行时刻。

    **Validates: Requirements 5.4, 13.3, 15.3, 16.4, 17.5**
    """
    ctx, formula = case

    # 起始 last_computed_at 概念上为 None（结果对象新建，尚未计算）。
    before = datetime.now(timezone.utc)
    result = _run(execute_formula(None, formula=formula, ctx=ctx, resolve_refs=False))
    after = datetime.now(timezone.utc)

    # 求值成功 → 目标单元被回填。
    assert result.updated_cells == [formula.target_cell]
    assert result.errors == []

    # 核心不变量：last_computed_at 从 None 被更新为一个 UTC 时区感知时间戳，
    # 且落在执行前后瞬间之间（即「本次执行时刻」）。
    ts = result.last_computed_at
    assert ts is not None, "auto_calc 成功执行必须记录 last_computed_at"
    assert ts.tzinfo is not None, "last_computed_at 必须是时区感知时间戳"
    assert before <= ts <= after, "last_computed_at 必须为本次执行时刻"


@given(_evaluatable_auto_calc())
@settings(max_examples=100)
def test_auto_calc_reexecution_advances_timestamp(case):
    """P9 补强：连续两次成功执行，last_computed_at 从旧值被更新为更晚的执行时刻。"""
    ctx, formula = case

    r1 = _run(execute_formula(None, formula=formula, ctx=ctx, resolve_refs=False))
    r2 = _run(execute_formula(None, formula=formula, ctx=ctx, resolve_refs=False))

    assert r1.last_computed_at is not None and r2.last_computed_at is not None
    # 每次执行生成独立结果对象，时间戳单调不减（旧值被更新为新执行时刻）。
    assert r2.last_computed_at >= r1.last_computed_at


@given(_unevaluatable_auto_calc())
@settings(max_examples=200)
def test_auto_calc_failure_writes_no_timestamp(case):
    """P9 失败分支：无法求值时保留原值、不回填、且 last_computed_at 保持 None。

    **Validates: Requirements 5.4**
    """
    ctx, formula = case
    before_row_cache = copy.deepcopy(ctx.row_cache)

    result = _run(execute_formula(None, formula=formula, ctx=ctx, resolve_refs=False))

    # 求值失败：记描述性错误、不回填目标单元。
    assert result.errors, "无法求值必须返回描述性错误"
    assert result.updated_cells == []
    assert result.values == {}
    # 核心不变量：失败的求值绝不写时间戳。
    assert result.last_computed_at is None, "求值失败不得写入 last_computed_at"
    # 目标单元原值（本例不存在则不应被创建）保持不变。
    assert ctx.row_cache == before_row_cache
    assert formula.target_cell not in ctx.row_cache
