"""真实 parser → 行计算 → 写入 → 生成批次；不使用共享引擎或应用启动。"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.report_generation_models import ReportGenerationRun
from app.services.formula_provenance import FinalValueProvenanceV1, input_digest
from app.services.report_engine import ReportFormulaParser
from app.services.report_freshness import CALC_VERSION
from app.services.report_provenance import (
    current_context, finish_generation, generation_context, run_display_status,
)
from app.services.report_row_compute import GenerateSummary, RowScope, compute_row, write_row
from tests.formula_integrity_support import add_note, add_report, add_wp, note_table, report_config
from tests.formula_integrity_support import integrity_world as integrity_world


class IntegrityAmountSource:
    """只替代 TB 数据读取一层；parser、来源发出、计算和写入都是真实现。"""

    def __init__(self, value=Decimal("4.25"), warning=False):
        self.value, self.warning, self.calls = value, warning, []

    async def resolve_tb(self, code, column):
        self.calls.append(("TB", code, column))
        if self.warning:
            from app.services.formula_warnings import emit

            emit({"message": "【测试】叶子口径提示"})
        return self.value

    async def resolve_sum(self, code, column):
        self.calls.append(("SUM_TB", code, column))
        return self.value


def input_values(inputs):
    return [(atom.kind, atom.key, Decimal(str(atom.value))) for atom in inputs]


def generation(world):
    return generation_context(world.db, project_id=world.project.id, year=2025,
        trigger="formula_integrity", triggered_by=None, calc_version=f"report:{CALC_VERSION}")


@pytest.mark.parametrize("zero", (False, True))
async def test_formula_integrity_compute_write_generation_records_actual_sources(integrity_world, zero):
    world = integrity_world
    tb, wp, prior, source_row = ((Decimal(0),) * 4 if zero else
                                (Decimal("4.25"), Decimal("23.50"), Decimal("7.25"), Decimal(5)))
    await add_wp(world, "E1", {"audited_amount": str(wp)})
    await add_note(world, note_table("999", str(prior)))
    source = IntegrityAmountSource(tb)
    parser = ReportFormulaParser(world.db, world.project.id, 2025, resolver=source)
    config = report_config(formula="TB('1001','审定数')+WP('E1','审定数')+"
        "NOTE('五、1','合计','期初')+ROW('BS001')")
    scope = RowScope.of([config, report_config("BS001")])
    cache = {"BS001": source_row}
    row = await add_report(world, config.row_code, Decimal(91), is_stale=True)
    summary, expected = GenerateSummary(), tb + wp + prior + source_row
    async with generation(world) as ctx:
        assert current_context() is ctx
        outcome = await compute_row(parser, config, cache, mode="audited", scope=scope)
        assert outcome.ok, outcome.errors
        assert outcome.value == expected
        assert cache[config.row_code] == expected
        assert input_values(outcome.inputs) == [
            ("TB", "1001|审定数", tb), ("WP", "E1|审定数", wp),
            ("NOTE", "NOTE('五、1','合计','期初')", prior), ("ROW", "BS001", source_row)]
        now = datetime.now(timezone.utc)
        write_row(row, config, outcome, generated_at=now, source_accounts=["1001"])
        summary.record(row.report_type, row.row_code, Decimal(91), outcome)
        await finish_generation(world.db, ctx, summary)
        assert row.current_period_amount == expected
        assert row.formula_used == config.formula
        assert row.source_accounts == ["1001"]
        assert row.calc_version == CALC_VERSION
        assert row.is_stale is False and row.calc_error is None
        assert row.run_id == ctx.run_id
        envelope = FinalValueProvenanceV1.model_validate(row.provenance)
        assert envelope.value_state == "auto" and envelope.calculation_applied
        assert envelope.applied_attempt == envelope.last_calculation
        attempt = envelope.applied_attempt
        assert attempt.run_id == ctx.run_id and attempt.calculation_status == "succeeded"
        assert Decimal(attempt.calculated_value) == expected
        assert attempt.input_count == 4
        assert attempt.input_digest == input_digest(outcome.inputs)
        assert sorted(input_values(attempt.inputs)) == sorted(input_values(outcome.inputs))
        assert all(atom.source_project_id == world.project.id for atom in attempt.inputs)
        run = await world.db.get(ReportGenerationRun, ctx.run_id)
        assert (run.changed_rows, run.recomputed_rows, run.failed_rows) == (1, 0, 0)
        assert run.finished_at is not None and run_display_status(run) == "succeeded"
        assert run.calc_version == CALC_VERSION
    assert current_context() is None
    await world.db.refresh(row)
    assert row.current_period_amount == expected
    assert UUID(row.provenance["applied_attempt"]["run_id"]) == row.run_id


@pytest.mark.parametrize("missing", ("WP('E1','审定数')", "NOTE('五、1','合计')"))
async def test_formula_integrity_failed_attempt_keeps_applied_value_and_prior_inputs(integrity_world, missing):
    world = integrity_world
    parser = ReportFormulaParser(world.db, world.project.id, 2025, resolver=IntegrityAmountSource(warning=True))
    original = report_config(formula="TB('1001','审定数')")
    cache, row = {}, await add_report(world, original.row_code, Decimal(91))
    async with generation(world) as first:
        outcome = await compute_row(parser, original, cache, mode="audited", scope=RowScope.of([original]))
        assert outcome.ok, outcome.errors
        write_row(row, original, outcome, generated_at=datetime.now(timezone.utc), source_accounts=["1001"])
        await world.db.flush()
        prior = deepcopy(row.provenance)
        prior_run = first.run_id
    stored = (row.current_period_amount, row.formula_used, row.calc_version, row.generated_at, row.source_accounts)
    failed = report_config(formula="TB('1001','审定数')+" + missing)
    summary = GenerateSummary()
    async with generation(world) as second:
        outcome = await compute_row(parser, failed, cache, mode="audited", scope=RowScope.of([failed]))
        assert not outcome.ok and outcome.value is None
        assert original.row_code not in cache
        assert input_values(outcome.inputs) == [("TB", "1001|审定数", Decimal("4.25"))]
        assert outcome.warnings == ["【测试】叶子口径提示"]
        assert ("底稿 E1" if missing.startswith("WP") else "NOTE") in "；".join(outcome.errors)
        write_row(row, failed, outcome, generated_at=datetime.now(timezone.utc), source_accounts=["9999"])
        summary.record(row.report_type, row.row_code, stored[0], outcome)
        await finish_generation(world.db, second, summary)
        assert (row.current_period_amount, row.formula_used, row.calc_version, row.generated_at, row.source_accounts) == stored
        assert row.run_id == prior_run
        assert row.is_stale and row.calc_error
        assert row.provenance["applied_attempt"] == prior["applied_attempt"]
        envelope = FinalValueProvenanceV1.model_validate(row.provenance)
        assert envelope.value_state == "auto" and not envelope.calculation_applied
        attempt = envelope.last_calculation
        assert attempt.attempt_id != envelope.applied_attempt.attempt_id
        assert attempt.run_id == second.run_id
        assert attempt.calculation_status == "failed" and attempt.calculated_value is None
        assert attempt.error_code == "REPORT_" + outcome.state.upper()
        assert attempt.input_digest == input_digest(outcome.inputs)
        assert sorted(input_values(attempt.inputs)) == sorted(input_values(outcome.inputs))
        run = await world.db.get(ReportGenerationRun, second.run_id)
        assert (run.changed_rows, run.recomputed_rows, run.failed_rows) == (0, 0, 1)
        assert run_display_status(run) == "partial" and run.error
    assert current_context() is None
    await world.db.refresh(row)
    assert row.current_period_amount == stored[0] and row.run_id == prior_run
    assert row.provenance["applied_attempt"] == prior["applied_attempt"]
    assert row.provenance["last_calculation"]["calculation_status"] == "failed"


async def test_formula_integrity_handoff_unselected_row_is_eagerly_prechecked(integrity_world):
    """如实锁定：IF 仅实际分支 → 条件恒真时未选分支不阻断、不读取。

    parser 短路 IF(1,...) 只走 then；上层 ``visit_rows`` 同口径，不预查 else
    引用的 BS001——即使 scope 里有它且 cache 里没它，也不应阻断。
    """
    world = integrity_world
    config = report_config(formula="IF(1,7,ROW('BS001'))")
    parser = ReportFormulaParser(world.db, world.project.id, 2025)
    direct = await parser.execute_with_status(config.formula, {})
    assert direct.ok and direct.value == Decimal(7)
    scope = RowScope.of([config, report_config("BS001", "1")])
    cache = {}
    outcome = await compute_row(parser, config, cache, mode="audited", scope=scope)
    # IF 仅实际分支：条件恒真时 BS001 未被访问 → 不阻断
    assert outcome.state == "ok" and outcome.value == Decimal(7)
    assert outcome.errors == []
    assert config.row_code in cache
