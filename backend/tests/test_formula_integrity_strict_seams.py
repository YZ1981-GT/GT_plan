"""Strict 生产接缝回归；只供隔离 runner 执行，不导入 app.main 或默认引擎。

内存 SQLite 来自 integrity_world；其余来源只替下一层读取，计算与写回均用生产函数。
技术失败的 attempt 与 run 仍属调用方事务，不宣称回滚后耐久。
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import AccountCategory, TbBalance, TrialBalance
from app.models.report_generation_models import ReportGenerationRun
from app.models.report_models import FinancialReport, FinancialReportType
from app.services import formula_engine as fe, report_engine as re, report_row_compute as rc
from app.services.formula_inputs import collect as collect_inputs
from app.services.formula_provenance import FinalValueProvenanceV1, input_digest
from app.services.report_freshness import CALC_VERSION
from app.services.report_provenance import generation_context
from tests.formula_integrity_support import add_report, report_config
from tests.formula_integrity_support import integrity_world as integrity_world

pytestmark = pytest.mark.asyncio
BS = FinancialReportType.balance_sheet


class MemoryRead:
    """只有显式队列，无引擎、网络或默认数据库回退。"""

    def __init__(self, *responses):
        self.responses, self.statements = list(responses), []
        self.rollback, self.commit = AsyncMock(), AsyncMock()

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.responses, "未声明的数据库读取"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return NS(all=lambda: list(response), scalars=lambda: NS(all=lambda: list(response)))


def config(formula="TB('1001','审定数')", code="BS999"):
    return report_config(code, formula, row_number=999, report_type=BS)


def generation(world):
    return generation_context(world.db, project_id=world.project.id, year=2025,
        trigger="strict_seams", triggered_by=None, calc_version=f"report:{CALC_VERSION}")


async def production_entry(world, monkeypatch, entry, cfg, summary, *, debug=False):
    monkeypatch.setattr(re.ReportEngine, "_load_report_configs", AsyncMock(return_value={BS: [cfg]}))
    monkeypatch.setattr(re.ReportEngine, "_resolve_row_refs_via_acnr", AsyncMock(return_value=([], [])))
    monkeypatch.setattr(re.ReportEngine, "_invalidate_report_cache", AsyncMock())
    engine = re.ReportEngine(world.db)
    if entry == "full":
        return await engine._generate_report(world.project.id, 2025, BS, [cfg], {},
            datetime.now(timezone.utc), prior_resolver=NS(prior_amount=AsyncMock(return_value=None)),
            scope=rc.RowScope.of([cfg]), summary=summary, debug=debug)
    if entry == "stale":
        return await engine.recalculate_stale_rows(world.project.id, 2025,
            applicable_standard="enterprise", summary_out=summary)
    return await engine.regenerate_affected(world.project.id, 2025, changed_accounts=["1001"],
        applicable_standard="enterprise", summary_out=summary)


class RecordingSummary(rc.GenerateSummary):
    def __init__(self):
        super().__init__()
        self.outcomes = []

    def record(self, report_type, row_code, before, outcome):
        super().record(report_type, row_code, before, outcome)
        self.outcomes.append(outcome)


def wrapped_error():
    cause = RuntimeError("【测试】来源读取故障")
    try:
        raise cause
    except RuntimeError as error:
        try:
            raise fe.FormulaEvalError("【测试】来源暂不可用") from error
        except fe.FormulaEvalError as wrapped:
            return wrapped, cause


@pytest.mark.parametrize("entry", ["full", "stale", "affected"])
async def test_production_strict_records_failed_attempt_before_original_raise(integrity_world, monkeypatch, entry):
    world, old = integrity_world, config("12.50")
    row = await add_report(world, old.row_code, Decimal("91"))
    async with generation(world):
        outcome = await rc.compute_row(re.ReportFormulaParser(world.db, world.project.id, 2025),
            old, {}, mode="audited", scope=rc.RowScope.of([old]), strict=True)
        rc.write_row(row, old, outcome, generated_at=datetime.now(timezone.utc), source_accounts=["旧来源"])
        await world.db.flush()
    prior = deepcopy(row.provenance)
    stored = (row.current_period_amount, row.formula_used, row.source_accounts,
              row.generated_at, row.calc_version, row.run_id)
    row.is_stale = True
    error, cause = wrapped_error()
    reads = []

    async def source(parser, code):
        reads.append((parser.project_id, parser.year, code))
        if code == "9999":
            raise error
        rows = [NS(standard_account_code="1001", audited_amount=Decimal("99")),
                NS(standard_account_code="100101", audited_amount=Decimal("7"))]
        parser._tb_prefix_cache[code] = rows
        return rows

    monkeypatch.setattr(re.ReportFormulaParser, "_get_tb_rows_prefix", source)
    cfg = config("TB('1001','审定数') + TB('9999','审定数')")
    summary = RecordingSummary()
    async with generation(world) as current:
        with collect_inputs() as inputs:
            with pytest.raises(fe.FormulaEvalError) as caught:
                await production_entry(world, monkeypatch, entry, cfg, summary)
        assert caught.value is error
        assert caught.value.__cause__ is cause
        assert len(summary.outcomes) == len(summary.failed_rows) == 1
        assert not summary.changed_rows and not summary.recomputed_rows
        failure = summary.outcomes[0]
        assert failure.value is None and failure.state == "error"
        assert failure.inputs == inputs and len(inputs) == 1
        assert [(a.kind, a.key, a.value) for a in inputs] == [("TB", "1001|审定数", "7")]
        assert len(failure.warnings) == 1 and "本级金额 99.00" in failure.warnings[0]
        assert "下级科目合计 7.00" in failure.warnings[0]
        envelope = FinalValueProvenanceV1.model_validate(row.provenance)
        assert not envelope.calculation_applied
        assert row.provenance["applied_attempt"] == prior["applied_attempt"]
        attempt = envelope.last_calculation
        assert attempt is not None and attempt.run_id == current.run_id
        assert attempt.calculation_status == "failed" and attempt.error_code == "REPORT_ERROR"
        assert attempt.calculated_value is None and attempt.input_count == 1
        assert attempt.inputs == inputs and attempt.input_digest == input_digest(inputs)
        assert attempt.definition_snapshot["formula"] == cfg.formula
        assert (row.current_period_amount, row.formula_used, row.source_accounts,
                row.generated_at, row.calc_version, row.run_id) == stored
        assert row.is_stale and row.calc_error == failure.calc_error
        run = await world.db.get(ReportGenerationRun, current.run_id)
        assert run.status == "building" and run.finished_at is None
    assert reads == [(world.project.id, 2025, "1001"), (world.project.id, 2025, "9999")]

@pytest.mark.parametrize("formula", [
    "IF(1,7,ROW('BS001'))",
    "IF(0,ROW('BS001'),7)",
    "IF(1,7,SUM_ROW('BS001','BS002'))",
    "IF(1,7,ADJ('1001'))",
])
async def test_unselected_reference_branch_never_reads_or_blocks(monkeypatch, formula):
    db = MemoryRead()
    parser = re.ReportFormulaParser(db, uuid4(), 2025)
    adjustments = AsyncMock(side_effect=AssertionError("不应读取未选中分支"))
    monkeypatch.setattr(parser, "_get_adj_data", adjustments)
    cfg = config(formula)
    scope = rc.RowScope.of([cfg, config("1", "BS001"), config("2", "BS002")])
    cache = {}
    result = await rc.compute_row(parser, cfg, cache, mode="audited", scope=scope, strict=True)
    assert result.ok and result.value == Decimal("7")
    assert cache == {cfg.row_code: Decimal("7")}
    assert result.inputs == [] and result.warnings == []
    assert result.substituted_expression is not None
    adjustments.assert_not_awaited()
    assert db.statements == [] and db.responses == []
    assert rc.current_report_evaluation() is None


@pytest.mark.parametrize("formula", ["ROW('BS002')", "SUM_ROW('BS001','BS002')"])
async def test_selected_reference_checks_full_scope_not_cached_subset(formula):
    db = MemoryRead()
    cfg = config(formula)
    scope = rc.RowScope.of([cfg, config("1", "BS001"), config("2", "BS002")])
    cache = {"BS001": Decimal("3"), cfg.row_code: Decimal("91")}
    result = await rc.compute_row(re.ReportFormulaParser(db, uuid4(), 2025), cfg, cache,
        mode="audited", scope=scope, strict=True)
    assert not result.ok and result.state == "not_ready" and result.value is None
    assert any("BS002" in error and "未就绪" in error for error in result.errors)
    assert cache == {"BS001": Decimal("3")}
    assert result.inputs == [] and db.statements == []
    assert rc.current_report_evaluation() is None

@pytest.mark.parametrize("raw", [None, "", "  ", True, "坏金额", "NaN", "Infinity", "-Infinity"])
async def test_parser_rejects_existing_invalid_tb_amount_without_retry(raw):
    db = MemoryRead([NS(standard_account_code="1001", audited_amount=raw)])
    parser = re.ReportFormulaParser(db, uuid4(), 2025)
    result = await parser.execute_with_status("TB('1001','审定数')", {}, strict=True)
    assert not result.ok and result.value is None and result.failure_kind == "business"
    assert result.technical_error is None and result.errors
    assert len(db.statements) == 1 and db.responses == []
    db.commit.assert_not_awaited()
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize("raw, expected_atom", [(0, "0"), ("0", "0"), (Decimal("0.00"), "0.00")])
async def test_parser_preserves_existing_zero_and_single_source_atom(raw, expected_atom):
    db = MemoryRead([NS(standard_account_code="1001", audited_amount=raw)])
    parser = re.ReportFormulaParser(db, uuid4(), 2025)
    with collect_inputs() as inputs:
        result = await parser.execute_with_status("TB('1001','审定数') + TB('1001','审定数')", {}, strict=True)
    assert result.ok and result.value == Decimal("0")
    assert len(inputs) == 1 and inputs[0].kind == "TB" and inputs[0].value == expected_atom
    assert inputs[0].key == "1001|审定数"
    assert len(db.statements) == 1 and db.responses == []


@pytest.mark.parametrize("formula", [
    "TB('1001','不存在的列')",
    "SUM_TB('1001~1009','不存在的列')",
    "SUM_TB('1009~1001','审定数')",
    "SUM_TB('1001','审定数')",
    "SUM_TB('~1001','审定数')",
])
async def test_invalid_column_or_range_is_business_failure_before_source_access(formula):
    db = MemoryRead()
    parser = re.ReportFormulaParser(db, uuid4(), 2025)
    resolver = NS(resolve_tb=AsyncMock(side_effect=AssertionError("无效地址不应取数")),
                  resolve_sum=AsyncMock(side_effect=AssertionError("无效地址不应取数")))
    parser.resolver = resolver
    result = await parser.execute_with_status(formula, {}, strict=True)
    assert not result.ok and result.value is None and result.failure_kind == "business"
    resolver.resolve_tb.assert_not_awaited()
    resolver.resolve_sum.assert_not_awaited()
    assert db.statements == []


async def test_selected_adj_loads_once_for_repeated_and_distinct_nodes(monkeypatch):
    parser = re.ReportFormulaParser(MemoryRead(), uuid4(), 2024)
    loader = AsyncMock(return_value={"1001": {"aje_net": Decimal("3.25"), "rje_net": Decimal("1.50")}})
    monkeypatch.setattr(parser, "_get_adj_data", loader)
    with collect_inputs() as inputs:
        result = await parser.execute_with_status(
            "ADJ('1001','aje_net') + ADJ('1001','aje_net') + ADJ('1001','rje_net')", {}, strict=True)
    assert result.ok and result.value == Decimal("8.00")
    loader.assert_awaited_once_with(strict=True)
    assert [(atom.kind, atom.key, atom.value) for atom in inputs] == [
        ("ADJ", "1001|aje_net", "3.25"), ("ADJ", "1001|rje_net", "1.50")]
    assert rc.current_report_evaluation() is None


async def test_selected_adj_failure_keeps_original_error_and_cause(monkeypatch):
    parser = re.ReportFormulaParser(MemoryRead(), uuid4(), 2025)
    error, cause = wrapped_error()
    loader = AsyncMock(side_effect=error)
    monkeypatch.setattr(parser, "_get_adj_data", loader)
    with pytest.raises(fe.FormulaEvalError) as caught:
        await parser.execute_with_status("ADJ('1001','aje_net')", {}, strict=True)
    assert caught.value is error and caught.value.__cause__ is cause
    loader.assert_awaited_once_with(strict=True)
    assert rc.current_report_evaluation() is None


async def test_opening_compatibility_entry_never_loads_current_adjustments(monkeypatch):
    parser = re.ReportFormulaParser(MemoryRead(), uuid4(), 2025)
    parser._use_opening = True
    loader = AsyncMock(side_effect=AssertionError("期初模式不应读取本年调整"))
    monkeypatch.setattr(parser, "_get_adj_data", loader)
    result = await parser.execute("ADJ('1001','aje_net')", {}, strict=True)
    assert result == Decimal("0")
    loader.assert_not_awaited()
    assert rc.current_report_evaluation() is None