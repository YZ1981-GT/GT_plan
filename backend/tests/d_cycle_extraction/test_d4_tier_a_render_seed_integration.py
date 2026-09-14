"""Wave 4 / Task 4.2 —— D4 营业收入 render Tier A **双标量** transient seed 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 3.1–3.7, 5.1 / Property 6, 7, 10, 11, 13)

D4 是唯一**双标量**循环：`resolve_effective` 返回两条 Tier A 绑定——
  * `D4-1-adj-tb-6001` = `TB('6001','审定数')`（主营业务收入审定发生额）
  * `D4-1-adj-tb-6051` = `TB('6051','审定数')`（其他业务收入审定发生额）
共享助手 `seed_tier_a_reconciliation` 的锚点遍历天然覆盖两条，各自独立 transient seed 进
`responses_snapshot`（不落库；手工优先；disabled 跳过；写对字段 remark；fail-open——单条
求值失败不影响另一条）。本测试**同时断言两个锚点**（task 4.2 要求 D4 覆盖 BOTH anchors）。

mock 调用方模块（d4）的 `resolve_effective`/`evaluate_wp_formula_expression`；evaluator 按
表达式区分 6001/6051 返回不同值，以证明两锚点各自正确 seed（非串值）。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.routers.wp_render_strategies import _d4_operating_revenue as d4
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
)

_ANCHOR_6001 = "D4-1-adj-tb-6001"
_ANCHOR_6051 = "D4-1-adj-tb-6051"
# 用非整数小数：format_cell_display_value 对整数 Decimal 归一为 int（去 .00），
# 故取带非零小数位的值使 seed remark == 字面量（对齐 D1-D7 单标量 test 的 98765.43）。
_VAL_6001 = "1200000.55"
_VAL_6051 = "88000.25"


def _run(coro):
    return asyncio.run(coro)


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeSession:
    def __init__(self, *, checklist_rows=None):
        self.checklist_rows = checklist_rows or []
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        self.executed_sql.append(s)
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(
                one=SimpleNamespace(
                    client_name="测试客户",
                    audit_year=2025,
                    business_category="general",
                )
            )
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id, *, conclusion="", remark=""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _ctx(db, *, year=2025):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=year,
        business_category="general",
        classification=SimpleNamespace(sheet_name="审定表D4-1"),
    )


def _binding(anchor, expression, *, source=SOURCE_PRESET):
    return {
        "wp_code": "D4",
        "sheet_name": "D4-1",
        "anchor": anchor,
        "expression": expression,
        "formula_type": "auto_calc",
        "description": "",
        "source": source,
        "tier": "A",
    }


def _dual_bindings(*, source_6001=SOURCE_PRESET, source_6051=SOURCE_PRESET):
    return [
        _binding(_ANCHOR_6001, "TB('6001','审定数')", source=source_6001),
        _binding(_ANCHOR_6051, "TB('6051','审定数')", source=source_6051),
    ]


def _mock_resolver(monkeypatch, bindings):
    async def _fake_resolve(db, wp_id, wp_code, project_id):
        return list(bindings)

    monkeypatch.setattr(d4, "resolve_effective", _fake_resolve)


def _mock_evaluator_by_expr(monkeypatch, *, fail_6001=False, errs_6051=False):
    """按表达式区分 6001/6051 返回不同值（证明两锚点各自正确 seed）。"""

    async def _fake_eval(db, *, project_id, year, expression, **kw):
        if "6001" in expression:
            if fail_6001:
                raise RuntimeError("6001 eval boom")
            return Decimal(_VAL_6001), []
        if "6051" in expression:
            if errs_6051:
                return Decimal("0"), ["6051 悬空引用"]
            return Decimal(_VAL_6051), []
        return Decimal("0"), []

    monkeypatch.setattr(d4, "evaluate_wp_formula_expression", _fake_eval)


def _enable(monkeypatch):
    monkeypatch.setattr(d4.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch):
    monkeypatch.setattr(d4.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 10: 灰度关闭零回归
# ---------------------------------------------------------------------------


def test_flag_off_no_seed_both_anchors(monkeypatch):
    """主开关关（默认）→ 两个锚点都不 seed。"""
    _disable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert _ANCHOR_6001 not in snap
    assert _ANCHOR_6051 not in snap


# ---------------------------------------------------------------------------
# 主机制：双标量各自 seed 到 remark（BOTH anchors）
# ---------------------------------------------------------------------------


def test_flag_on_seeds_both_anchors_to_remark(monkeypatch):
    """主开关开 → 6001 与 6051 **各自**独立 seed 到 remark（值不串）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == _VAL_6001, "6001 主营审定发生额 seed"
    assert snap[_ANCHOR_6051]["remark"] == _VAL_6051, "6051 其他审定发生额 seed"
    assert snap[_ANCHOR_6001].get("conclusion", "") == ""
    assert snap[_ANCHOR_6051].get("conclusion", "") == ""


def test_edited_custom_formula_takes_effect_6001(monkeypatch):
    """编辑即生效：6001 用户 custom 公式覆盖预设 → seed 按新公式；6051 仍按预设。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings(source_6001=SOURCE_CUSTOM))
    _mock_evaluator_by_expr(monkeypatch)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == _VAL_6001
    assert snap[_ANCHOR_6051]["remark"] == _VAL_6051


# ---------------------------------------------------------------------------
# 手工优先（Property 6 / R3.2）——逐锚点独立
# ---------------------------------------------------------------------------


def test_manual_priority_per_anchor(monkeypatch):
    """6001 持久层已有非空 remark → 不覆盖；6051 空 → 仍 seed（逐锚点独立手工优先）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch)
    checklist = [_checklist_row(_ANCHOR_6001, remark="999999")]
    snap = _run(d4.render(_ctx(_FakeSession(checklist_rows=checklist))))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == "999999", "6001 手工值不被覆盖"
    assert snap[_ANCHOR_6051]["remark"] == _VAL_6051, "6051 空 → 仍 seed"


# ---------------------------------------------------------------------------
# disabled 跳过（R3.3）——逐锚点独立
# ---------------------------------------------------------------------------


def test_disabled_per_anchor(monkeypatch):
    """6051 disabled → 不 seed；6001 preset → 仍 seed（逐锚点独立）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings(source_6051=SOURCE_DISABLED))
    _mock_evaluator_by_expr(monkeypatch)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == _VAL_6001
    assert _ANCHOR_6051 not in snap


# ---------------------------------------------------------------------------
# fail-open（Property 11 / R3.4）——单条失败不影响另一条
# ---------------------------------------------------------------------------


def test_failopen_one_anchor_eval_error_other_still_seeds(monkeypatch):
    """6001 求值异常 → 不 seed；6051 正常 → 仍 seed（单条失败不牵连另一条 / Property 11）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch, fail_6001=True)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert _ANCHOR_6001 not in snap, "6001 求值异常 → 不 seed"
    assert snap[_ANCHOR_6051]["remark"] == _VAL_6051, "6051 不受 6001 失败影响"


def test_failopen_one_anchor_eval_errors_other_still_seeds(monkeypatch):
    """6051 有 eval_errors → 不 seed；6001 正常 → 仍 seed（不静默落错误/0，R3.4）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch, errs_6051=True)
    snap = _run(d4.render(_ctx(_FakeSession())))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == _VAL_6001
    assert _ANCHOR_6051 not in snap


def test_failopen_resolver_error(monkeypatch):
    """resolver 异常 → 两锚点都不 seed（fail-open），render 不阻断。"""
    _enable(monkeypatch)

    async def _boom(*a, **kw):
        raise RuntimeError("resolve boom")

    monkeypatch.setattr(d4, "resolve_effective", _boom)
    _mock_evaluator_by_expr(monkeypatch)
    result = _run(d4.render(_ctx(_FakeSession())))
    assert _ANCHOR_6001 not in result["responses_snapshot"]
    assert _ANCHOR_6051 not in result["responses_snapshot"]
    assert "project_context" in result


def test_failopen_year_none(monkeypatch):
    """year 缺失 → 两锚点都不 seed（fail-open）。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch)
    snap = _run(d4.render(_ctx(_FakeSession(), year=None)))["responses_snapshot"]
    assert _ANCHOR_6001 not in snap
    assert _ANCHOR_6051 not in snap


# ---------------------------------------------------------------------------
# Property 13: seed 全程 transient 不落库
# ---------------------------------------------------------------------------


def test_seed_is_transient_no_db_write(monkeypatch):
    """双标量 seed 只进返回 payload，render 对 checklist_responses 只 SELECT，无 INSERT/UPDATE。"""
    _enable(monkeypatch)
    _mock_resolver(monkeypatch, _dual_bindings())
    _mock_evaluator_by_expr(monkeypatch)
    db = _FakeSession()
    snap = _run(d4.render(_ctx(db)))["responses_snapshot"]
    assert snap[_ANCHOR_6001]["remark"] == _VAL_6001
    assert snap[_ANCHOR_6051]["remark"] == _VAL_6051
    joined = " ".join(db.executed_sql)
    assert "insert into" not in joined and "update " not in joined, (
        "D4 双标量 transient seed 不得写 checklist_responses/DB（Property 13）"
    )
