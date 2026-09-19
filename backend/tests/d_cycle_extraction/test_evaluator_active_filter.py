"""Wave 2 / Task 3.1 + 3.2 —— 评估器口径统一 + Tier A 不支持函数拒绝.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/ 决策3（方案 a）

覆盖：
  * **Property 3**（R1.3/R4.1）：`_resolve_tb`/`_resolve_sum_tb` 改用
    `get_active_filter`（数据集版本口径），与 Tier B prefill 同口径；
    不再裸 `is_deleted`。断言 get_active_filter 被以 TrialBalance 表调用。
  * **Property 10**（R4.3）：同一四表库快照下多次求值同一 Tier A 公式结果一致（幂等）。
  * **Property 6**（R4.2）：`find_unsupported_formula_functions` 检出
    AUX/PREV/序时账（LEDGER/COUNT_LEDGER），TB/SUM_TB/WP 放行——供保存端点返 422。

测试用 fake async session（不依赖真实 PG / SQLite），monkeypatch
`get_active_filter` 隔离数据集过滤逻辑并捕获调用参数。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa

from app.models.audit_platform_models import TrialBalance
from app.services import wp_formula_eval_service as eval_mod
from app.services.wp_formula_eval_service import (
    _resolve_sum_tb,
    _resolve_tb,
    evaluate_wp_formula_expression,
    find_unsupported_formula_functions,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async session（返回预置 TrialBalance 行）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeTbSession:
    """execute 恒回预置的 TrialBalance 行（模拟"active-dataset-filtered 查询结果"）。"""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.execute_count = 0

    async def execute(self, stmt, params=None):
        self.execute_count += 1
        return _FakeResult(self._rows)


def _tb_row(code, *, audited=0.0, opening=0.0, unadjusted=0.0):
    return SimpleNamespace(
        standard_account_code=code,
        audited_amount=Decimal(str(audited)),
        opening_balance=Decimal(str(opening)),
        unadjusted_amount=Decimal(str(unadjusted)),
        rje_adjustment=Decimal("0"),
        aje_adjustment=Decimal("0"),
    )


def _patch_active_filter(monkeypatch):
    """monkeypatch get_active_filter，捕获调用参数并返回一个真值过滤条件。"""
    calls: list[dict] = []

    async def _fake_filter(db, table, project_id, year, **kw):
        calls.append(
            {"table": table, "project_id": project_id, "year": year, "kw": kw}
        )
        return sa.true()

    monkeypatch.setattr(eval_mod, "get_active_filter", _fake_filter)
    return calls


# ---------------------------------------------------------------------------
# Property 3: active_filter 同口径（不再裸 is_deleted）
# ---------------------------------------------------------------------------


def test_property3_resolve_tb_uses_active_filter(monkeypatch):
    calls = _patch_active_filter(monkeypatch)
    pid, year = uuid4(), 2025
    sess = _FakeTbSession([_tb_row("1402", audited=1234.5)])

    val = _run(_resolve_tb(sess, pid, year, "1402", "期末余额"))

    assert val == Decimal("1234.5")
    # 断言经 get_active_filter 且以 TrialBalance 表 / 同 (project, year) 调用
    assert len(calls) == 1
    assert calls[0]["table"] is TrialBalance.__table__
    assert calls[0]["project_id"] == pid
    assert calls[0]["year"] == year


def test_property3_resolve_sum_tb_uses_active_filter(monkeypatch):
    calls = _patch_active_filter(monkeypatch)
    pid, year = uuid4(), 2025
    sess = _FakeTbSession(
        [_tb_row("1402.01", audited=100.0), _tb_row("1402.02", audited=200.0)]
    )

    val = _run(_resolve_sum_tb(sess, pid, year, "1402~1403", "期末余额"))

    assert val == Decimal("300.0")
    assert len(calls) == 1
    assert calls[0]["table"] is TrialBalance.__table__
    assert calls[0]["project_id"] == pid
    assert calls[0]["year"] == year


def test_property3_resolve_tb_column_map_opening(monkeypatch):
    """列名映射保持：期初余额 → opening_balance。"""
    _patch_active_filter(monkeypatch)
    sess = _FakeTbSession([_tb_row("1402", audited=1.0, opening=999.0)])
    val = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期初余额"))
    assert val == Decimal("999.0")


def test_property3_resolve_tb_missing_row_returns_zero(monkeypatch):
    """无行 → 0（不报错）。"""
    _patch_active_filter(monkeypatch)
    sess = _FakeTbSession([])
    val = _run(_resolve_tb(sess, uuid4(), 2025, "9999", "期末余额"))
    assert val == Decimal("0")


def test_property3_sum_tb_bad_range_returns_zero(monkeypatch):
    """非法范围（无 ~）→ 0，不调 active_filter。"""
    calls = _patch_active_filter(monkeypatch)
    sess = _FakeTbSession([_tb_row("1402", audited=100.0)])
    val = _run(_resolve_sum_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    assert val == Decimal("0")
    assert calls == []


# ---------------------------------------------------------------------------
# Property 10: 求值幂等（同快照多次求值一致）
# ---------------------------------------------------------------------------


def test_property10_resolve_tb_idempotent(monkeypatch):
    _patch_active_filter(monkeypatch)
    sess = _FakeTbSession([_tb_row("1402", audited=555.5)])
    v1 = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    v2 = _run(_resolve_tb(sess, uuid4(), 2025, "1402", "期末余额"))
    assert v1 == v2 == Decimal("555.5")


def test_property10_evaluate_expression_idempotent(monkeypatch):
    """整表达式 TB(...) 经统一口径求值，重复调用结果一致。"""
    _patch_active_filter(monkeypatch)
    pid, year = uuid4(), 2025
    sess = _FakeTbSession([_tb_row("1402", audited=2000.0)])

    v1, e1 = _run(
        evaluate_wp_formula_expression(
            sess, project_id=pid, year=year, expression="TB('1402','期末余额')"
        )
    )
    v2, e2 = _run(
        evaluate_wp_formula_expression(
            sess, project_id=pid, year=year, expression="TB('1402','期末余额')"
        )
    )
    assert v1 == v2 == Decimal("2000.0")
    assert e1 == e2 == []


def test_property10_sum_tb_expression_flows_through_active_filter(monkeypatch):
    """SUM_TB 表达式端到端经 active_filter 求值出合计。"""
    calls = _patch_active_filter(monkeypatch)
    sess = _FakeTbSession(
        [_tb_row("1402.01", audited=100.0), _tb_row("1402.02", audited=250.0)]
    )
    val, errs = _run(
        evaluate_wp_formula_expression(
            sess,
            project_id=uuid4(),
            year=2025,
            expression="SUM_TB('1402~1403','期末余额')",
        )
    )
    assert val == Decimal("350.0")
    assert errs == []
    assert calls[0]["table"] is TrialBalance.__table__


# ---------------------------------------------------------------------------
# Property 6: 不支持函数检出（AUX / PREV / 序时账）→ 供保存端点返 422
# ---------------------------------------------------------------------------


def test_property6_detects_aux():
    assert find_unsupported_formula_functions("AUX('1122','客户','期末余额')") == ["AUX"]


def test_property6_detects_prev():
    assert find_unsupported_formula_functions("PREV('D2','sheet','B5')") == ["PREV"]


def test_property6_detects_ledger():
    assert find_unsupported_formula_functions("LEDGER('6001','credit','全年')") == [
        "LEDGER"
    ]


def test_property6_detects_count_ledger_not_ledger():
    """COUNT_LEDGER 命中 COUNT_LEDGER 而非 LEDGER（词边界正确）。"""
    hits = find_unsupported_formula_functions("COUNT_LEDGER('6001','1-6月')")
    assert hits == ["COUNT_LEDGER"]


def test_property6_detects_multiple():
    hits = find_unsupported_formula_functions(
        "TB('1402','期末余额') + AUX('1122','客户','期末余额') + PREV('D2','s','B5')"
    )
    assert set(hits) == {"AUX", "PREV"}


def test_property6_supported_functions_pass():
    """TB/SUM_TB/WP + 字面量/四则运算不被拒绝。"""
    assert find_unsupported_formula_functions("TB('1402','期末余额')") == []
    assert find_unsupported_formula_functions("SUM_TB('1402~1403','期末余额')") == []
    assert find_unsupported_formula_functions("WP('D2','坏账准备明细表D2-3','合计')") == []
    assert find_unsupported_formula_functions("TB('1402','期末余额') * 1.13") == []
    assert find_unsupported_formula_functions("=TB('1402','期末余额')") == []


def test_property6_empty_and_none():
    assert find_unsupported_formula_functions("") == []
    assert find_unsupported_formula_functions(None) == []
    assert find_unsupported_formula_functions("   ") == []


def test_property6_no_false_positive_on_substring():
    """含 'AUX'/'PREV' 子串但非函数调用（无括号）不误伤。"""
    # 描述性文本、无 '(' → 不命中
    assert find_unsupported_formula_functions("TB('AUXCODE','期末余额')") == []
    assert find_unsupported_formula_functions("1234.5") == []
