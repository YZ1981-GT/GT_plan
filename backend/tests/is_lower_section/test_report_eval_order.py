from types import SimpleNamespace

import pytest

from app.services.report_eval_order import REPORT_TYPE_ORDER, eval_order


def row(code: str, number: int, formula: str | None = None, report_type: str = "income_statement"):
    return SimpleNamespace(row_code=code, row_number=number, formula=formula, report_type=report_type)


def codes(result) -> list[str]:
    return [item.row_code for item in result.order]


def test_without_dependencies_keeps_stable_report_and_row_order():
    rows = [row("IS-002", 2), row("BS-002", 2, report_type="balance_sheet"), row("IS-001", 1)]
    result = eval_order(rows)
    assert codes(result) == ["BS-002", "IS-001", "IS-002"]
    assert result.cycles == ()


def test_forward_row_reference_moves_dependency_before_total():
    rows = [
        row("IS-007", 7, "ROW('IS-008')+ROW('IS-009')"),
        row("IS-008", 8, "TB('6401','本期发生额')"),
        row("IS-009", 9),
    ]
    result = eval_order(rows)
    assert codes(result) == ["IS-008", "IS-009", "IS-007"]
    assert result.cycles == ()


def test_sum_row_expands_all_existing_members_in_range():
    rows = [
        row("IS-053", 53, "SUM_ROW('IS-054','IS-056')"),
        row("IS-054", 54, "ROW('IS-056')"),
        row("IS-055", 55),
        row("IS-056", 56),
    ]
    result = eval_order(rows)
    assert codes(result).index("IS-056") < codes(result).index("IS-054") < codes(result).index("IS-053")
    assert codes(result).index("IS-055") < codes(result).index("IS-053")


def test_cross_report_dependency_overrides_type_tie_break():
    rows = [
        row("BS-900", 1, "ROW('IS-900')", report_type="balance_sheet"),
        row("IS-900", 1, None, report_type="income_statement"),
    ]
    assert codes(eval_order(rows)) == ["IS-900", "BS-900"]


def test_cycle_reports_only_actual_cycle_members_and_keeps_all_rows():
    rows = [
        row("IS-001", 1, "ROW('IS-002')"),
        row("IS-002", 2, "ROW('IS-001')"),
        row("IS-003", 3, "ROW('IS-002')"),
        row("IS-004", 4),
    ]
    result = eval_order(rows)
    assert set(codes(result)) == {"IS-001", "IS-002", "IS-003", "IS-004"}
    assert result.cycles == ("IS-001", "IS-002")
    assert codes(result)[0] == "IS-004"


def test_self_reference_is_cycle_but_dangling_reference_is_not():
    result = eval_order([row("IS-001", 1, "ROW('IS-001')"), row("IS-002", 2, "ROW('MISSING')")])
    assert result.cycles == ("IS-001",)
    assert codes(result)[0] == "IS-002"


def test_duplicate_row_codes_fail_closed():
    with pytest.raises(ValueError, match="行次重复"):
        eval_order([row("IS-001", 1), row("IS-001", 2)])


def test_type_order_matches_report_engine_contract():
    from app.models.report_models import FinancialReportType

    assert REPORT_TYPE_ORDER == tuple(item.value for item in FinancialReportType)


# ─── 循环引用：compute_row 必须 fail-closed，不写假数（ADR-ISL-01）───────────────


class _CountingParser:
    """记下被调用次数的 parser 替身：环上的行不该走到求值。"""

    resolver = "synthetic"

    def __init__(self):
        self.calls: list[str] = []

    async def execute_with_status(self, formula: str, row_cache):  # noqa: ANN001
        from app.services.report_engine import evaluate_formula_result

        self.calls.append(formula)
        return await evaluate_formula_result(formula, resolver=self, row_cache=row_cache)

    async def resolve_tb(self, account_code: str, column_name: str):
        from decimal import Decimal

        _ = account_code, column_name
        return Decimal("100.00")

    async def resolve_sum(self, code_range: str, column_name: str):
        from decimal import Decimal

        _ = code_range, column_name
        return Decimal("0.00")


def _cycle_scope():
    from app.services.report_row_compute import RowScope

    rows = [row("IS-001", 1, "ROW('IS-002')"), row("IS-002", 2, "ROW('IS-001')"),
            row("IS-003", 3, "TB('6001','本期发生额')")]
    plan = eval_order(rows)
    return rows, plan, RowScope.of(rows, cycles=plan.cycles)


async def test_cycle_rows_fail_closed_without_evaluating():
    from app.services.report_row_compute import compute_row

    rows, plan, scope = _cycle_scope()
    assert set(plan.cycles) == {"IS-001", "IS-002"}
    parser = _CountingParser()
    cache: dict = {}
    outcome = await compute_row(parser, rows[0], cache, mode="audited", scope=scope)
    assert outcome.ok is False
    assert outcome.state == "cycle"
    assert outcome.value is None, "环上的行写了值：会把假数当审定数落库"
    assert "循环引用" in (outcome.calc_error or "")
    assert "IS-001" in outcome.calc_error and "IS-002" in outcome.calc_error
    assert parser.calls == [], "环上的行仍被送去求值"
    assert "IS-001" not in cache, "环上的行进了依赖缓存，引用它的行会读到假数"


async def test_cycle_row_already_in_cache_is_evicted():
    """上一轮留在缓存里的值必须被删掉 —— 否则引用它的行照旧读到陈旧值。"""
    from decimal import Decimal

    from app.services.report_row_compute import compute_row

    rows, _plan, scope = _cycle_scope()
    cache = {"IS-001": Decimal("999.00")}
    outcome = await compute_row(_CountingParser(), rows[0], cache, mode="audited", scope=scope)
    assert outcome.ok is False
    assert "IS-001" not in cache


async def test_non_cycle_row_still_evaluates_normally():
    """阴性对照：同一 scope 下不在环上的行照常求值（证明判据不是对任何行都失败）。"""
    from decimal import Decimal

    from app.services.report_row_compute import compute_row

    rows, _plan, scope = _cycle_scope()
    parser = _CountingParser()
    cache: dict = {}
    outcome = await compute_row(parser, rows[2], cache, mode="audited", scope=scope)
    assert outcome.ok is True
    assert outcome.value == Decimal("100.00")
    assert parser.calls == ["TB('6001','本期发生额')"]
    assert cache["IS-003"] == Decimal("100.00")
