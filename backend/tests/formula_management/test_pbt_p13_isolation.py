# Feature: formula-management-library, Property 13: 单条公式失败不阻断批次其余执行
"""属性测试 P13：单条公式失败不阻断批次其余执行（Task 2.7）。

**Property 13: 单条公式失败不阻断批次其余执行**

被测：``app.services.formula_management.engine.execute_formula`` 的逐条独立执行语义
（design §Components 2 / Data Models §5）。``execute_formula`` 每次只处理一条公式，
「批次」即调用方对一组公式的逐条循环。本属性以 Hypothesis 随机生成一批公式（含至少
一条无法求值 + 若干可求值，随机交错顺序），逐条执行并断言：

1. 整批循环**不抛异常**、每条都被执行（批次不被单条失败中断）。
2. **可求值**公式全部照常完成（记 ``last_computed_at``；auto_calc 正常回填目标单元）。
3. **无法求值**的失败项被隔离处理，不污染其余：
   - auto_calc  → 记描述性错误、保留原值不回填、不写时间戳；
   - logic_check → 追加一条标注「公式无法求值」的 Issue（不静默跳过，Req 6.6）；
   - reasonability → 记 WARNING 跳过该提示、不产生 Hint、不中断（Req 7.5）。

其中 Req 15.5 / 16.5 覆盖报表增量重算 / 报表生成场景下「悬空/失败引用记 Issue_List
并继续处理其余行」的同一隔离契约——底层均落在 ``execute_formula`` 的逐条隔离语义。

Validates: Requirements 6.6, 7.5, 15.5, 16.5
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import (
    FormulaRecord,
    execute_formula,
)

# 三类型公式。
_FTYPES = ["auto_calc", "logic_check", "reasonability"]

# 可求值表达式（引用 ctx 预载的 r1/r2，或纯字面量；均能被 L1 内核成功求值）。
_OK_EXPRS = [
    "ROW('r1') + ROW('r2')",
    "ROW('r1') - ROW('r2')",
    "100 + 50",
    "ROW('r1') >= ROW('r2')",
    "ROW('r1') < ROW('r2')",
    "ROW('r1') * 2",
]

# 无法求值表达式（语法非法，L1 内核解析失败 → fr.ok == False，绝不抛出）。
_BAD_EXPRS = [
    "1 + * 2",
    "* 3",
    "1 2 3",
    ") 5 (",
]


@st.composite
def _batches(draw):
    """随机一批公式规格：>=1 条无法求值 + 0..5 条可求值，顺序随机交错。

    每项为 ``(kind, formula_type, expression)``，``kind`` ∈ {"ok", "bad"}。
    """
    n_ok = draw(st.integers(min_value=0, max_value=5))
    n_bad = draw(st.integers(min_value=1, max_value=3))  # 至少一条失败
    specs: list[tuple[str, str, str]] = []
    for _ in range(n_ok):
        specs.append(
            ("ok", draw(st.sampled_from(_FTYPES)), draw(st.sampled_from(_OK_EXPRS)))
        )
    for _ in range(n_bad):
        specs.append(
            ("bad", draw(st.sampled_from(_FTYPES)), draw(st.sampled_from(_BAD_EXPRS)))
        )
    return draw(st.permutations(specs))


async def _run_batch(specs: list[tuple[str, str, str]]):
    """逐条执行一批公式，返回 ``(kind, ftype, result, record)`` 列表。

    单条失败绝不中断循环——若 execute_formula 抛出，测试会自然失败。
    """
    ctx = FormulaContext(row_cache={"r1": Decimal("100"), "r2": Decimal("50")})
    out = []
    for idx, (kind, ftype, expr) in enumerate(specs):
        rec = FormulaRecord(
            id=f"{kind}-{idx}",
            formula_type=ftype,
            target_cell=f"C{idx}",  # 唯一且非四表库单元
            expression=expr,
            issue_description=f"issue-{idx}",
            hint_text=f"hint-{idx}",
        )
        res = await execute_formula(None, formula=rec, ctx=ctx, resolve_refs=False)
        out.append((kind, ftype, res, rec))
    return out


@given(specs=_batches())
def test_p13_single_failure_does_not_block_batch(specs):
    results = asyncio.run(_run_batch(specs))

    # 批次未被中断：每条公式都被执行。
    assert len(results) == len(specs)

    for kind, ftype, res, rec in results:
        if kind == "ok":
            # 可求值公式照常完成（求值成功 → 记 last_computed_at）。
            assert res.last_computed_at is not None
            if ftype == "auto_calc":
                assert res.updated_cells == [rec.target_cell]
                assert res.errors == []
            elif ftype == "logic_check":
                # 可求值 logic_check 绝不产生「公式无法求值」项。
                assert all(
                    "公式无法求值" not in iss.description for iss in res.issues
                )
        else:  # kind == "bad" —— 无法求值，隔离处理，不影响其余。
            assert res.last_computed_at is None  # 未成功求值 → 不写时间戳
            if ftype == "auto_calc":
                assert res.errors  # 记描述性错误
                assert res.updated_cells == []  # 保留原值不回填
            elif ftype == "logic_check":
                # 追加一条标注「公式无法求值」的问题项（不静默跳过，Req 6.6）。
                assert len(res.issues) == 1
                assert "公式无法求值" in res.issues[0].description
            else:  # reasonability：记 WARNING 跳过该提示、不产生 Hint（Req 7.5）。
                assert res.hints == []
