"""属性测试 P12：四表库叶子源只读（Task 2.6）。

# Feature: formula-management-library, Property 12: 四表库叶子源只读
# 对任意目标地址，若目标为四表库（trial_balance / tb_balance / tb_ledger /
# tb_aux_balance）单元，则 auto_calc 回填型公式的定义被拒绝；四表库仅可被
# TB()/PREV()/AUX() 经 get_active_filter 读取。

被测：
- ``four_table_source.is_four_table_target`` / ``guard_four_table_leaf_readonly``
  （定义/保存期只读守卫，Req 12.2）
- ``engine.execute_formula`` 执行期兜底（auto_calc 目标为四表库 → 跳过回填、
  记描述性错误、绝不改值）

策略：Hypothesis 随机生成四表库目标地址（trial_balance / tb_balance / tb_ledger /
tb_aux_balance 各形态：表名 / URI 前缀 / 取数函数 / 索引命名空间）+ 随机 formula_type。
断言：
- 目标为四表库 + auto_calc → guard 抛 FourTableReadonlyError；执行期跳过回填不改值。
- 目标为四表库但非 auto_calc（logic_check / reasonability）→ 放行（可只读引用）。
- 目标非四表库 → 任意 formula_type 均放行；auto_calc 正常回填。

**Validates: Requirements 12.1, 12.2**
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import FormulaRecord, execute_formula
from app.services.formula_management.four_table_source import (
    FourTableReadonlyError,
    guard_four_table_leaf_readonly,
    is_four_table_target,
)


# ─────────────────────────────── 生成器 ───────────────────────────────
# 科目编码（1~6 打头 4 位，覆盖资产/负债/权益/损益各段）。
_account_codes = st.from_regex(r"[1-6][0-9]{3}", fullmatch=True)
_columns = st.sampled_from(["期末余额", "审定数", "年初余额", "本期发生额"])
_aux_members = st.sampled_from(["客户", "供应商", "部门", "项目"])
_formula_types = st.sampled_from(["auto_calc", "logic_check", "reasonability"])


@st.composite
def four_table_targets(draw) -> str:
    """随机四表库目标地址（覆盖四张表 + 全部识别形态）。"""
    code = draw(_account_codes)
    col = draw(_columns)
    member = draw(_aux_members)
    return draw(
        st.sampled_from(
            [
                # 直接含四表库表名
                f"trial_balance/{code}/{col}",
                f"tb_balance:{code}",
                "tb_ledger",
                f"tb_aux_balance/{code}/{member}",
                # ACNR 非 wp 域 URI 前缀
                f"tb://{code}#{col}",
                f"aux://{code}#{member}",
                # 取数公式函数起始
                f"TB('{code}','{col}')",
                f"PREV('{code}','{col}')",
                f"AUX('{code}','{member}')",
                f"SUM_TB('{code}~{code}','{col}')",
                # 索引命名空间前缀
                f"TB:{code}",
                f"aux:{code}",
            ]
        )
    )


@st.composite
def non_four_table_targets(draw) -> str:
    """随机非四表库目标地址（底稿单元 / 报表行 / 附注 / 裸单元）。"""
    code = draw(_account_codes)
    return draw(
        st.sampled_from(
            [
                f"WP('D2','明细表D2-2','E{code}')",
                f"report/BS/{code}",
                f"note:五、{code}",
                "C1",
                f"ROW('IS-{code}')",
            ]
        )
    )


# ─────────────────── 守卫层：四表库 + auto_calc → 拒绝（Req 12.2）───────────────────
@settings(max_examples=60)
@given(target=four_table_targets(), ftype=_formula_types)
def test_guard_rejects_auto_calc_allows_others_on_four_table(target, ftype):
    # 四表库地址一律被识别（Req 12.1：四表库为叶子源）。
    assert is_four_table_target(target) is True
    if ftype == "auto_calc":
        # auto_calc 回填型 → 只读守卫拒绝（Req 12.2）。
        with pytest.raises(FourTableReadonlyError):
            guard_four_table_leaf_readonly(formula_type=ftype, target=target)
    else:
        # logic_check / reasonability 不改值 → 放行（可只读引用四表库）。
        guard_four_table_leaf_readonly(formula_type=ftype, target=target)


@settings(max_examples=40)
@given(target=non_four_table_targets(), ftype=_formula_types)
def test_guard_allows_all_types_on_non_four_table(target, ftype):
    # 非四表库地址 → 不被识别为四表库，任意 formula_type 均放行。
    assert is_four_table_target(target) is False
    guard_four_table_leaf_readonly(formula_type=ftype, target=target)  # 不抛


# ─────────────── 执行期兜底：auto_calc 目标为四表库 → 跳过回填不改值 ───────────────
@settings(max_examples=40)
@given(target=four_table_targets())
def test_execute_auto_calc_four_table_skips_backfill_no_mutation(target):
    ctx = FormulaContext(row_cache={"r1": Decimal("100")})
    before = dict(ctx.row_cache)
    applied: dict[str, Decimal] = {}
    f = FormulaRecord(
        id="f-ft",
        formula_type="auto_calc",
        target_cell=target,
        expression="ROW('r1')",
    )
    res = asyncio.run(
        execute_formula(
            None,
            formula=f,
            ctx=ctx,
            apply_value=lambda c, v: applied.__setitem__(c, v),
            resolve_refs=False,
        )
    )
    assert res.errors  # 记描述性错误（四表库叶子源只读）
    assert res.updated_cells == []  # 未回填
    assert res.values == {}
    assert res.last_computed_at is None  # 不写时间戳
    assert applied == {}  # 未调用回填回调
    assert ctx.row_cache == before  # 绝不改值


@settings(max_examples=40)
@given(target=non_four_table_targets())
def test_execute_auto_calc_non_four_table_backfills(target):
    # 非四表库目标 → 未触发只读兜底 → auto_calc 正常求值回填。
    ctx = FormulaContext(row_cache={"r1": Decimal("100")})
    f = FormulaRecord(
        id="f-ok",
        formula_type="auto_calc",
        target_cell=target,
        expression="ROW('r1')",
    )
    res = asyncio.run(execute_formula(None, formula=f, ctx=ctx, resolve_refs=False))
    assert res.updated_cells == [target]
    assert res.values[target] == Decimal("100")
    assert res.last_computed_at is not None
    assert not any("四表库" in e for e in res.errors)
