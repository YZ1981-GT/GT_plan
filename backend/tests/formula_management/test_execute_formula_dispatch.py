"""单元测试：execute_formula 三类型分派 + 结果结构（Task 2.2）。

覆盖：
- auto_calc 求值回填目标单元 + 记 last_computed_at；失败保留原值不写时间戳。
- logic_check 不通过追加 Issue；无法求值追加「公式无法求值」项；绝不改值。
- reasonability 触发追加 Hint；无法求值记 WARNING 跳过不中断；绝不改值。
- resolve_ref fail-open：ACNR 异常返回 found=False 且不抛。

Requirements: 5.1, 5.2, 5.4, 5.5, 6.1, 6.2, 6.6, 7.1, 7.2, 7.5, 11.1, 11.2, 11.3
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.formula_engine import FormulaContext
from app.services.formula_management import engine
from app.services.formula_management.engine import (
    FormulaRecord,
    HintItem,
    IssueItem,
    execute_formula,
    resolve_ref,
)


def _ctx() -> FormulaContext:
    return FormulaContext(row_cache={"r1": Decimal("100"), "r2": Decimal("50")})


# ─────────────────────────── auto_calc ───────────────────────────
@pytest.mark.asyncio
async def test_auto_calc_backfills_target_and_records_time():
    ctx = _ctx()
    applied: dict[str, Decimal] = {}
    f = FormulaRecord(
        id="f-auto",
        formula_type="auto_calc",
        target_cell="C1",
        expression="ROW('r1') + ROW('r2')",
    )
    res = await execute_formula(
        None, formula=f, ctx=ctx, apply_value=lambda c, v: applied.__setitem__(c, v),
        resolve_refs=False,
    )
    assert res.updated_cells == ["C1"]
    assert res.values["C1"] == Decimal("150")
    assert ctx.row_cache["C1"] == Decimal("150")  # 回填到上下文
    assert applied == {"C1": Decimal("150")}
    assert res.last_computed_at is not None
    assert res.issues == [] and res.hints == [] and res.errors == []


@pytest.mark.asyncio
async def test_auto_calc_eval_failure_keeps_value_no_timestamp():
    ctx = _ctx()
    ctx.row_cache["C1"] = Decimal("999")  # 既有原值
    f = FormulaRecord(
        id="f-bad",
        formula_type="auto_calc",
        target_cell="C1",
        expression="1 + * 2",  # 解析错误 → 求值失败
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert res.errors  # 描述性错误
    assert res.updated_cells == []
    assert res.last_computed_at is None  # 不写时间戳
    assert ctx.row_cache["C1"] == Decimal("999")  # 保留原值不变


# ─────────────────────────── logic_check ───────────────────────────
@pytest.mark.asyncio
async def test_logic_check_pass_no_issue_no_mutation():
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-lc-pass",
        formula_type="logic_check",
        target_cell="X",
        expression="ROW('r1') >= ROW('r2')",  # 100>=50 → 通过
        issue_description="资产必须≥负债",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert res.issues == []
    assert ctx.row_cache == before  # 绝不改值
    assert res.last_computed_at is not None


@pytest.mark.asyncio
async def test_logic_check_fail_appends_issue_no_mutation():
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-lc-fail",
        formula_type="logic_check",
        target_cell="X",
        expression="ROW('r1') <= ROW('r2')",  # 100<=50 → 不通过
        issue_description="资产必须≤负债（示例）",
        addr_id="report/BS/1",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert len(res.issues) == 1
    issue = res.issues[0]
    assert isinstance(issue, IssueItem)
    assert issue.description == "资产必须≤负债（示例）"
    assert issue.addr_id == "report/BS/1"
    assert ctx.row_cache == before  # 绝不改值


@pytest.mark.asyncio
async def test_logic_check_uneval_appends_cannot_evaluate_issue():
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-lc-err",
        formula_type="logic_check",
        target_cell="X",
        expression="1 + * 2",  # 无法求值
        issue_description="平衡校验",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert len(res.issues) == 1  # 不静默跳过
    assert "公式无法求值" in res.issues[0].description
    assert res.last_computed_at is None
    assert ctx.row_cache == before  # 绝不改值


# ─────────────────────────── reasonability ───────────────────────────
@pytest.mark.asyncio
async def test_reasonability_triggered_appends_hint_no_mutation():
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-r-trig",
        formula_type="reasonability",
        target_cell="X",
        expression="ROW('r1') > ROW('r2')",  # 触发
        hint_text="数值偏高，请复核",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert len(res.hints) == 1
    assert isinstance(res.hints[0], HintItem)
    assert res.hints[0].hint_text == "数值偏高，请复核"
    assert ctx.row_cache == before  # 绝不改值


@pytest.mark.asyncio
async def test_reasonability_not_triggered_no_hint():
    ctx = _ctx()
    f = FormulaRecord(
        id="f-r-notrig",
        formula_type="reasonability",
        target_cell="X",
        expression="ROW('r1') < ROW('r2')",  # 不触发
        hint_text="不应出现",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert res.hints == []
    assert res.last_computed_at is not None


@pytest.mark.asyncio
async def test_reasonability_uneval_warns_and_skips(caplog):
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-r-err",
        formula_type="reasonability",
        target_cell="X",
        expression="1 + * 2",  # 无法求值
        hint_text="x",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert res.hints == []  # 跳过该提示
    assert res.last_computed_at is None
    assert ctx.row_cache == before  # 不中断、不改值


# ─────────────────────────── unknown type ───────────────────────────
@pytest.mark.asyncio
async def test_unknown_type_returns_error_no_mutation():
    ctx = _ctx()
    before = dict(ctx.row_cache)
    f = FormulaRecord(
        id="f-unknown",
        formula_type="mystery",
        target_cell="X",
        expression="ROW('r1')",
    )
    res = await execute_formula(None, formula=f, ctx=ctx, resolve_refs=False)
    assert res.errors
    assert res.updated_cells == []
    assert ctx.row_cache == before


# ─────────────────────────── resolve_ref fail-open ───────────────────────────
@pytest.mark.asyncio
async def test_resolve_ref_fail_open_on_acnr_error(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("ACNR down")

    monkeypatch.setattr("app.services.acnr.resolver.full_resolve", _boom)
    rr = await resolve_ref(formula_ref="WP('D2','明细表D2-2','E100')", project_id="p1")
    assert rr.found is False
    assert rr.error == "acnr_unavailable_fallback"


@pytest.mark.asyncio
async def test_execute_formula_resolves_refs_via_resolve_ref(monkeypatch):
    calls: list[dict] = []

    async def _fake_resolve(**kwargs):
        calls.append(kwargs)

        class _R:
            found = True
            addr_id = kwargs.get("addr_id") or "report/BS/1"

        return _R()

    monkeypatch.setattr(engine, "resolve_ref", _fake_resolve)
    ctx = _ctx()
    f = FormulaRecord(
        id="f-refs",
        formula_type="auto_calc",
        target_cell="C1",
        expression="ROW('r1')",
        refs=[{"formula_ref": "WP('D2','s','E1')"}, {"addr_id": "report/BS/2"}, "TB('1001')"],
    )
    res = await execute_formula(None, formula=f, ctx=ctx, project_id="p1", resolve_refs=True)
    assert len(calls) == 3  # 每条引用都经 resolve_ref
    assert res.values["C1"] == Decimal("100")
