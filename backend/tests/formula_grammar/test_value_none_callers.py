"""ADR-FGR-03 调用方失败输入：失败值必须留空，并保留可读原因。"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.formula_engine import FormulaContext, FormulaResult, execute, execute_formula
from app.services.report_config_execute import _payload
from app.services.report_engine import ReportFormulaParser, evaluate_formula
from app.services.report_row_compute import RowScope, compute_row


def test_execute_formula_returns_none_on_failure() -> None:
    assert execute_formula("ROW('missing')", {}, {}) is None


def test_l1_failure_has_none_value_and_reason() -> None:
    result = execute("ROW('missing')", FormulaContext())
    assert result.ok is False
    assert result.value is None
    assert result.errors


@pytest.mark.asyncio
async def test_report_parser_and_wrapper_return_none_on_failure() -> None:
    parser = ReportFormulaParser(None, UUID("00000000-0000-0000-0000-000000000001"), 2025)
    assert await parser.execute("ROW('missing')", {}) is None
    assert await evaluate_formula("ROW('missing')", resolver=parser, row_cache={}) is None


def test_report_payload_preserves_failure_reason_and_null_value() -> None:
    result = _payload(FormulaResult(errors=["引用行未就绪"]), [])
    assert result["ok"] is False
    assert result["value"] is None
    assert result["error"] == "引用行未就绪"


@pytest.mark.asyncio
async def test_report_row_failure_is_blank() -> None:
    class Parser:
        async def execute_with_status(self, formula, row_cache):
            return FormulaResult(errors=["引用行未就绪"])

    config = SimpleNamespace(row_code="R2", formula="ROW('R1')")
    outcome = await compute_row(Parser(), config, {}, mode="audited", scope=RowScope(frozenset(), frozenset()))
    assert outcome.ok is False
    assert outcome.value is None
    assert outcome.errors == ["引用行未就绪"]


def test_successful_zero_remains_zero() -> None:
    result = execute("0", FormulaContext())
    assert result.ok is True
    assert result.value == Decimal("0")


@pytest.mark.asyncio
async def test_deprecated_parser_returns_reason_on_failure() -> None:
    from app.services.formula_parse_utils import FormulaEvaluator, FuncCallNode, StringNode

    evaluator = FormulaEvaluator(None, UUID("00000000-0000-0000-0000-000000000002"), 2025)
    with pytest.raises(ValueError, match="不存在|未返回数值"):
        await evaluator._eval_func(FuncCallNode("ROW", [StringNode("missing")]))


@pytest.mark.asyncio
async def test_unadjusted_report_keeps_failed_value_blank(monkeypatch) -> None:
    import app.services.report_engine as report_engine
    import app.services.report_prior_period as prior_period
    from app.models.report_models import FinancialReportType

    class FailingParser:
        def __init__(self, *args, **kwargs):
            self._use_unadjusted = False

        async def execute(self, formula, row_cache):
            return None

    class EmptyPrior:
        def __init__(self, *args, **kwargs):
            pass

        async def prior_amount(self, report_type, config):
            return None

    async def no_refs(*args, **kwargs):
        return {}, set()

    monkeypatch.setattr(report_engine, "ReportFormulaParser", FailingParser)
    monkeypatch.setattr(prior_period, "PriorPeriodResolver", EmptyPrior)
    config = SimpleNamespace(
        row_number=1, row_code="BS-001", row_name="测试行", formula="ROW('missing')",
        indent_level=0, is_total_row=False,
    )
    engine = SimpleNamespace(db=None, _resolve_row_refs_via_acnr=no_refs)
    rows = await report_engine.ReportEngine._compute_unadjusted_report_rows(
        engine, UUID("00000000-0000-0000-0000-000000000003"), 2025,
        FinancialReportType.balance_sheet, [config], {}, {},
    )
    assert rows[0]["current_period_amount"] is None
    assert rows[0]["formula_error"] == "公式执行未返回数值"


@pytest.mark.asyncio
async def test_cross_check_failure_has_reason() -> None:
    from app.services.formula_settings.cross_check_rules import _evaluate

    value, reason = await _evaluate("ROW('missing')", object(), {})
    assert value is None
    assert reason


@pytest.mark.asyncio
async def test_consol_row_failure_is_blank() -> None:
    from app.services.consol_report_values import BasisResolver, ReportRow, _Pass
    from app.services.report_engine import evaluate_formula

    row = ReportRow("balance_sheet", "BS-001", "测试行", 1, "ROW('missing')")
    outcome = await _Pass([row], BasisResolver({}), require_linear=False).value(row, evaluate_formula)
    assert outcome.amount is None
    assert outcome.reason


@pytest.mark.asyncio
async def test_prior_period_failure_is_blank(monkeypatch) -> None:
    from app.services.report_prior_period import PriorPeriodResolver
    from app.models.report_models import FinancialReportType

    resolver = PriorPeriodResolver(None, UUID("00000000-0000-0000-0000-000000000004"), 2025)

    async def unavailable():
        return False

    monkeypatch.setattr(resolver, "_opening_available", unavailable)
    config = SimpleNamespace(formula="ROW('missing')", row_code="BS-001")
    assert await resolver.prior_amount(FinancialReportType.balance_sheet, config) is None


@pytest.mark.asyncio
async def test_trim_failure_is_unavailable(monkeypatch) -> None:
    import app.services.trim_report_line_amounts as trim
    from app.services.four_table.report_line_index import REF_RESOLVED, ReportLineRef

    async def standard(*args, **kwargs):
        return "soe_standalone", ""

    async def configs(*args, **kwargs):
        return {"R1": {"row_name": "测试行", "formula": "ROW('missing')"}}, set()

    class FailingParser:
        def __init__(self, *args, **kwargs):
            pass

        def extract_row_refs(self, formula):
            return []

        async def execute(self, formula, row_cache):
            return None

        def extract_account_codes(self, formula):
            return []

    monkeypatch.setattr(trim, "_resolve_project_standard", standard)
    monkeypatch.setattr(trim, "_fetch_report_lines", configs)
    monkeypatch.setattr(trim, "resolve_report_line_ref", lambda raw, *hints: ReportLineRef(
        wp_code="D1", row_code="R1", status=REF_RESOLVED, source_symbol="test",
    ))
    monkeypatch.setattr(trim, "ReportFormulaParser", FailingParser)
    result = await trim.resolve_trim_report_line_amounts(None, UUID("00000000-0000-0000-0000-000000000005"), 2025, ["D1"])
    assert result["D1"].amount is None
    assert result["D1"].status == trim.AMOUNT_FORMULA_UNAVAILABLE
    assert result["D1"].reason


@pytest.mark.asyncio
async def test_prefill_failure_returns_none(monkeypatch) -> None:
    import app.services.formula_preloader as preloader
    from app.services.formula_engine import FormulaContext
    from app.services.prefill_engine import resolve_extended_formula

    async def empty_context(*args, **kwargs):
        return FormulaContext()

    monkeypatch.setattr(preloader, "preload", empty_context)
    assert await resolve_extended_formula(
        None, UUID("00000000-0000-0000-0000-000000000006"), 2025,
        "ROW", "'missing'",
    ) is None


@pytest.mark.asyncio
async def test_prefill_cell_failure_is_recorded(monkeypatch, tmp_path) -> None:
    import openpyxl
    import app.services.formula_preloader as preloader
    import app.services.formula_settings.wp_effective as effective
    from app.services.formula_engine import FormulaContext
    from app.services.prefill_engine import prefill_workpaper_real

    workbook_path = tmp_path / "failure.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active["A1"] = "=ROW('missing')"
    workbook.save(workbook_path)
    workbook.close()

    wp = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000007"),
        file_path=str(workbook_path), parsed_data=None, prefill_tb_snapshot=None,
    )

    class QueryResult:
        def scalar_one_or_none(self):
            return wp

    class Db:
        async def execute(self, *args, **kwargs):
            return QueryResult()

        async def flush(self):
            return None

    async def empty_context(*args, **kwargs):
        return FormulaContext()

    async def no_overlay(*args, **kwargs):
        return args[4], []

    monkeypatch.setattr(preloader, "preload", empty_context)
    monkeypatch.setattr(effective, "overlay_prefill_formulas", no_overlay)
    result = await prefill_workpaper_real(
        Db(), UUID("00000000-0000-0000-0000-000000000008"), 2025, wp.id,
    )
    assert result["formulas_filled"] == 0
    assert result["errors"]
    assert "missing" in result["errors"][0]["error"]


@pytest.mark.asyncio
async def test_trial_balance_formula_failure_is_blank(monkeypatch) -> None:
    import app.services.adjustment_amount_source as adjustment_source
    import app.services.report_config_service as config_service
    import app.services.tb_formula_context as tb_context
    from app.services.trial_balance_service import TrialBalanceService

    rc_row = SimpleNamespace(
        row_code="BS-001", row_name="测试行", indent_level=0, is_total_row=False,
        formula="ROW('missing')", aje_formula=None, rje_formula=None,
    )

    class QueryResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return list(self._rows)

    class Db:
        def __init__(self):
            self.calls = 0

        async def execute(self, query, *args, **kwargs):
            self.calls += 1
            return QueryResult([rc_row] if self.calls == 1 else [])

    async def standard(*args, **kwargs):
        return "soe_standalone"

    async def no_adjustments(*args, **kwargs):
        return {}

    async def empty_tb(*args, **kwargs):
        return {}

    monkeypatch.setattr(config_service.ReportConfigService, "resolve_applicable_standard", staticmethod(standard))
    monkeypatch.setattr(adjustment_source, "adj_net_batch", no_adjustments)
    monkeypatch.setattr(tb_context, "build_tb_formula_data", empty_tb)
    rows = await TrialBalanceService(Db()).get_summary_with_adjustments(
        UUID("00000000-0000-0000-0000-000000000009"), 2025,
    )
    assert rows[0]["unadjusted"] is None
    assert rows[0]["audited"] is None
    assert rows[0]["formula_error"]


@pytest.mark.asyncio
async def test_trial_balance_adjustment_failure_falls_back(monkeypatch) -> None:
    import app.services.adjustment_amount_source as adjustment_source
    import app.services.report_config_service as config_service
    import app.services.tb_formula_context as tb_context
    from app.services.trial_balance_service import TrialBalanceService

    rc_row = SimpleNamespace(
        row_code="BS-001", row_name="测试行", indent_level=0, is_total_row=False,
        formula="1", aje_formula="ROW('missing')", rje_formula=None,
    )

    class QueryResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return list(self._rows)

    class Db:
        def __init__(self):
            self.calls = 0

        async def execute(self, query, *args, **kwargs):
            self.calls += 1
            return QueryResult([rc_row] if self.calls == 1 else [])

    async def standard(*args, **kwargs):
        return "soe_standalone"

    async def no_adjustments(*args, **kwargs):
        return {}

    async def empty_tb(*args, **kwargs):
        return {}

    monkeypatch.setattr(config_service.ReportConfigService, "resolve_applicable_standard", staticmethod(standard))
    monkeypatch.setattr(adjustment_source, "adj_net_batch", no_adjustments)
    monkeypatch.setattr(tb_context, "build_tb_formula_data", empty_tb)
    rows = await TrialBalanceService(Db()).get_summary_with_adjustments(
        UUID("00000000-0000-0000-0000-000000000010"), 2025,
    )
    assert rows[0]["unadjusted"] == 1.0
    assert rows[0]["audited"] == 1.0
    assert rows[0]["formula_error"] is None


@pytest.mark.asyncio
async def test_central_failure_is_null(monkeypatch) -> None:
    import app.services.formula_central_execute as central
    from app.services.formula_engine import FormulaContext

    async def empty_context(*args, **kwargs):
        return FormulaContext()

    async def no_missing(*args, **kwargs):
        return []

    monkeypatch.setattr(central, "preload", empty_context)
    monkeypatch.setattr(central, "missing_account_codes", no_missing)
    result = await central.execute_central(
        None, UUID("00000000-0000-0000-0000-000000000011"), 2025, "ROW('missing')",
    )
    assert result["ok"] is False
    assert result["value"] is None
    assert result["errors"]


def test_custom_function_failure_is_blocked() -> None:
    from app.services.formula_custom_functions import (
        register_custom_function, unregister_custom_function,
    )
    from app.services.formula_engine import FormulaContext, execute

    name = "R3_FAILURE_CASE"
    unregister_custom_function(name)
    register_custom_function(name, "ROW('missing')")
    try:
        result = execute(f"{name}()", FormulaContext())
        assert result.ok is False
        assert result.value is None
        assert result.errors
    finally:
        unregister_custom_function(name)


def _management_failure_formula(formula_type: str):
    from app.services.formula_management.engine import FormulaRecord

    return FormulaRecord(
        id=f"r3-{formula_type}", formula_type=formula_type,
        target_cell="cell-1", expression="ROW('missing')",
        issue_description="测试失败公式", hint_text="测试失败提示", addr_id="cell-1",
    )


def test_formula_management_auto_calc_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import _exec_auto_calc

    result = _exec_auto_calc(_management_failure_formula("auto_calc"), FormulaContext(), None)
    assert result.errors
    assert result.values == {}
    assert result.last_computed_at is None


def test_formula_management_logic_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import _exec_logic_check

    result = _exec_logic_check(_management_failure_formula("logic_check"), FormulaContext())
    assert result.issues
    assert "无法求值" in result.issues[0].description


def test_formula_management_reasonability_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import _exec_reasonability

    result = _exec_reasonability(_management_failure_formula("reasonability"), FormulaContext())
    assert result.hints == []
    assert result.last_computed_at is None


def _batch_failure_formula(formula_type: str):
    from app.services.formula_management.engine import BatchFormulaDefinition

    return BatchFormulaDefinition(
        id=f"batch-r3-{formula_type}", formula_type=formula_type,
        expression="ROW('missing')", addr_id="cell-1",
        issue_description="批量测试失败公式", hint_text="批量测试失败提示",
    )


def test_formula_management_batch_auto_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import BatchExecutionResult, _batch_exec_auto_calc

    result = BatchExecutionResult()
    _batch_exec_auto_calc(_batch_failure_formula("auto_calc"), FormulaContext(), result)
    assert result.errors
    assert result.intents == []


def test_formula_management_batch_logic_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import BatchExecutionResult, _batch_exec_logic_check

    result = BatchExecutionResult()
    _batch_exec_logic_check(_batch_failure_formula("logic_check"), FormulaContext(), result)
    assert result.issues
    assert result.issues[0]["passed"] is False


def test_formula_management_batch_reasonability_failure() -> None:
    from app.services.formula_engine import FormulaContext
    from app.services.formula_management.engine import BatchExecutionResult, _batch_exec_reasonability

    result = BatchExecutionResult()
    _batch_exec_reasonability(_batch_failure_formula("reasonability"), FormulaContext(), result)
    assert result.hints == []


def _push_failure_rule(code: str):
    from app.services.formula_push.rules import PushRule, PushSource, PushTarget

    return PushRule(
        rule_id=f"{code}.failure", page_key=f"workpaper:{code}", stage="source", policy="system",
        target=PushTarget(domain="workpaper", wp_code=code, sheet_code=f"{code}-1",
                          item_id=f"{code}-value", fields=("value",)),
        source=PushSource(kind="formula", expression="ROW('missing')"),
        triggers=("manual",), description="R3 失败输入",
    )


def _empty_formula_sources():
    from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

    return FormulaSources(tb=TbAuditedSnapshot({}, True))


def test_formula_push_tier_a_failure_skips() -> None:
    from app.services.formula_push.bindings.tier_a import TierAAnchorBinding, TierASources

    binding = TierAAnchorBinding("D1", ("1001",))
    targets, skips = binding.workpaper_targets(
        _push_failure_rule("D1"), {}, TierASources(_empty_formula_sources()),
    )
    assert targets == []
    assert skips and "公式求值失败" in skips[0].reason


def test_formula_push_note_failure_skips() -> None:
    from app.services.formula_push.bindings.note_direct import NoteDirectBinding, NoteDirectSources

    binding = NoteDirectBinding("G1", ("1001",), "测试科目")
    targets, skips = binding.workpaper_targets(
        _push_failure_rule("G1"), {}, NoteDirectSources(_empty_formula_sources()),
    )
    assert targets == []
    assert skips and "公式求值失败" in skips[0].reason


def test_formula_push_k1_failure_skips() -> None:
    from app.services.formula_push.bindings.k1 import K1Binding, K1Sources

    binding = K1Binding()
    targets, skips = binding.workpaper_targets(
        _push_failure_rule("K1"), {}, K1Sources(_empty_formula_sources()),
    )
    assert targets == []
    assert skips and "公式求值失败" in skips[0].reason


def test_formula_push_e1_failure_skips() -> None:
    from app.services.formula_push.bindings.e1 import E1Binding, E1Sources

    binding = E1Binding()
    sources = E1Sources({}, {}, _empty_formula_sources(), None)
    targets, skips = binding.workpaper_targets(_push_failure_rule("E1"), {}, sources)
    assert targets == []
    assert skips and "公式求值失败" in skips[0].reason


def test_formula_push_balance_failure_skips() -> None:
    from app.services.formula_push.bindings.balance_adj import (
        AdjudicationSpec, BalanceAdjSources, BalanceAdjudicationBinding,
    )

    binding = BalanceAdjudicationBinding(AdjudicationSpec(
        wp_code="K2", account_codes=("1001",), sheet_code="K2-1",
        has_provision=False, dynamic_rows=True,
    ))
    targets, skips = binding.workpaper_targets(
        _push_failure_rule("K2"), {}, BalanceAdjSources(_empty_formula_sources()),
    )
    assert targets == []
    assert skips and "公式求值失败" in skips[0].reason


@pytest.mark.asyncio
async def test_formula_debug_failure_exposes_reason(monkeypatch) -> None:
    import app.routers.formula_debug as debug
    from app.services.formula_engine import FormulaContext

    async def empty_context(*args, **kwargs):
        return FormulaContext()

    monkeypatch.setattr(debug, "_build_context", empty_context)
    body = SimpleNamespace(formula="ROW('missing')", scope="report", custom_context=None, year=2025)
    response = await debug._debug_run(None, UUID("00000000-0000-0000-0000-000000000012"), body)
    assert response.ok is False
    assert response.value is None
    assert response.errors


def test_formula_result_value_is_nullable_decimal() -> None:
    from typing import get_args, get_type_hints
    from app.services.formula_engine import FormulaResult

    annotation = get_type_hints(FormulaResult)["value"]
    assert Decimal in get_args(annotation)
    assert type(None) in get_args(annotation)
