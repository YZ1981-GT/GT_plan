from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.formula_provenance import (
    FinalValueProvenanceV1,
    InputAtom,
    advance_final_value,
    build_attempt,
    definition_identity,
    redact_inputs_for_projects,
    push_rule_identity,
)

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_PROJECT = UUID("00000000-0000-0000-0000-000000000002")


def _identity():
    return definition_identity(
        version=3,
        layer="project",
        kind="report_config",
        source_id="cfg-3",
        snapshot={"formula": "TB('1001','期末余额')"},
    )


def _attempt(*, status: str = "succeeded", value=Decimal("12.30")):
    return build_attempt(
        domain="report",
        identity=_identity(),
        run_id=RUN_ID,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        computed_by=None,
        calc_version="report:229",
        inputs=[InputAtom(kind="TB", key="1001", value="12.30")],
        calculated_value=value if status == "succeeded" else None,
        calculation_status=status,
        error_code=None if status == "succeeded" else "FORMULA_FAILED",
    )


def test_attempt_carries_rebuildable_definition_and_calculated_value():
    attempt = _attempt()
    assert attempt.definition_ref == {"kind": "report_config", "id": "cfg-3"}
    assert attempt.definition_snapshot == {"formula": "TB('1001','期末余额')"}
    assert attempt.calculated_value == "12.30"
    assert attempt.calculation_status == "succeeded"


def test_unapplied_attempt_preserves_the_current_applied_attempt():
    applied = _attempt()
    current = advance_final_value(
        None, value_slot="current", value_state="auto", attempt=applied, calculation_applied=True,
    )
    failed = _attempt(status="failed")
    next_value = advance_final_value(
        current, value_slot="current", value_state="locked", attempt=failed, calculation_applied=False,
    )
    assert next_value.applied_attempt is not None
    assert next_value.applied_attempt.attempt_id == applied.attempt_id
    assert next_value.last_calculation is not None
    assert next_value.last_calculation.attempt_id == failed.attempt_id
    assert next_value.calculation_applied is False


def test_applied_final_value_rejects_failed_or_nonlatest_attempts():
    failed = _attempt(status="failed")
    with pytest.raises(ValueError, match="成功"):
        advance_final_value(None, value_slot="current", value_state="auto", attempt=failed, calculation_applied=True)
    with pytest.raises(ValueError, match="最近一次"):
        FinalValueProvenanceV1(
            value_state="auto", calculation_applied=True, applied_attempt=_attempt(), last_calculation=_attempt(),
        )


def test_cross_project_input_is_redacted_without_changing_original_digest():
    visible = InputAtom(kind="TB", key="1001", value="1.00")
    hidden = InputAtom(kind="TB", key="子项目-1002", value="2.00", source_project_id=OTHER_PROJECT)
    redacted, did_redact = redact_inputs_for_projects([visible, hidden], allowed_project_ids=set())
    assert did_redact is True
    assert redacted[0] == visible
    assert redacted[1].value is None and redacted[1].source_ref is None


def test_unsupported_input_object_is_rejected():
    with pytest.raises(TypeError, match="不支持"):
        build_attempt(
            domain="report", identity=_identity(), run_id=RUN_ID,
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), computed_by=None,
            calc_version="report:229", inputs=[{"kind": "TB", "key": "1001", "value": object()}],
            calculated_value=Decimal("1"), calculation_status="succeeded",
        )


def test_input_coverage_matrix_declares_all_three_execution_domains():
    path = Path(__file__).with_name("formula_provenance_input_matrix.json")
    matrix = json.loads(path.read_text(encoding="utf-8"))
    assert matrix["schema_version"] == 1
    assert {"report", "note", "push"} <= set(matrix)
    assert {"TB", "SUM_TB", "ROW", "SUM_ROW", "ADJ", "WP", "NOTE"} <= set(matrix["report"]["emitted"])
    assert set(matrix["report"]["unsupported_zero_not_emitted"]) == {"AUX", "PREV"}
    assert {"CELL", "TB", "REPORT", "NOTE", "WP", "PRIOR", "AGING"} <= set(matrix["note"]["emitted"])
    assert {"TB", "FOUR_TABLE", "DERIVED", "ADJ"} <= set(matrix["push"]["emitted"])


def test_push_identity_hash_ignores_description_but_tracks_execution_fields():
    def rule(*, description: str, expression: str):
        return SimpleNamespace(
            rule_id="E1.amount", page_key="wp:E1", stage="after", policy="editable",
            target={"domain": "workpaper", "fields": ["amount"]},
            source={"kind": "formula", "expression": expression}, triggers=("manual",),
            description=description, version=1, status="active",
        )

    baseline = push_rule_identity(rule(description="说明 A", expression="TB('1001')"), "r" * 64)
    renamed = push_rule_identity(rule(description="说明 B", expression="TB('1001')"), "r" * 64)
    changed = push_rule_identity(rule(description="说明 A", expression="TB('1002')"), "r" * 64)
    assert baseline.definition_hash == renamed.definition_hash
    assert baseline.definition_hash != changed.definition_hash


@pytest.mark.parametrize("outcome_ok", [True, False])
def test_report_write_row_maintains_applied_and_last_calculation(monkeypatch, outcome_ok: bool):
    from app.services import report_row_compute

    context = SimpleNamespace(
        run_id=RUN_ID,
        triggered_by=None,
        calc_version="report:2",
    )
    monkeypatch.setattr(report_row_compute, "_report_context", lambda: context)
    config = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        report_type="balance_sheet", row_code="BS-001", row_name="货币资金",
        indent_level=1, is_total_row=False, formula="TB('1001','期末余额')",
        formula_category="auto_calc", formula_version=3,
        effective_definition_version=3, effective_definition_layer="global",
        effective_source_id="cfg-3", applicable_standard="soe",
    )
    row = SimpleNamespace(
        row_name="旧", indent_level=0, is_total_row=False,
        current_period_amount=Decimal("10.00"), formula_used="旧",
        source_accounts=None, generated_at=None, calc_version=1,
        calc_error=None, is_stale=False, provenance=None, run_id=None,
    )
    if outcome_ok:
        report_row_compute.write_row(
            row, config, report_row_compute.RowOutcome(value=Decimal("12.30")),
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), source_accounts=["1001"],
        )
        final = FinalValueProvenanceV1.model_validate(row.provenance)
        assert final.calculation_applied is True
        assert final.applied_attempt is not None
        assert final.last_calculation is not None
        assert row.run_id == RUN_ID
    else:
        report_row_compute.write_row(
            row, config, report_row_compute.RowOutcome(state="error", errors=["坏公式"]),
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc), source_accounts=["1001"],
        )
        final = FinalValueProvenanceV1.model_validate(row.provenance)
        assert final.calculation_applied is False
        assert final.applied_attempt is None
        assert final.last_calculation is not None
        assert final.last_calculation.calculation_status == "failed"
        assert row.current_period_amount == Decimal("10.00")


@pytest.mark.asyncio
async def test_push_state_write_persists_unapplied_calculation_attempt():
    from datetime import datetime, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.models.formula_push_models import FormulaPushState
    from app.services.formula_push import engine as push_engine
    from app.services.formula_push.results import RunResult
    from app.services.formula_provenance import push_rule_identity

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    project_id = UUID("00000000-0000-0000-0000-000000000010")
    run_id = UUID("00000000-0000-0000-0000-000000000011")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FormulaPushState.__table__.create)
        async with AsyncSession(engine) as db:
            rule = SimpleNamespace(rule_id="E1.amount", page_key="wp:E1", stage="source", policy="editable", version=1)
            ctx = push_engine._Ctx(
                db=db, project_id=project_id, year=2025, triggered_by=None,
                force=frozenset(), now=datetime(2026, 1, 1, tzinfo=timezone.utc), states={},
                result=RunResult(project_id=project_id, year=2025, trigger="manual"),
                ruleset_hash="r" * 64,
            )
            ctx.state_writes.append(push_engine._StateWrite(
                addr_id="E1/sheet/item.amount", rule_id="E1.amount", domain="workpaper",
                wp_id=None, note_section=None, formula_value=Decimal("12.30"), current_after=Decimal("10.00"),
                state="locked", record_pushed=False, forced=False,
                definition_identity=push_rule_identity(rule, ctx.ruleset_hash),
                inputs=[InputAtom(kind="TB", key="1001|期末余额", value="12.30")],
                calculation_applied=False,
            ))
            await push_engine._save_states(ctx, run_id)
            state = ctx.states["E1/sheet/item.amount"]
            assert state.provenance["calculation_applied"] is False
            assert state.provenance["value_state"] == "locked"
            assert state.provenance["last_calculation"]["calculated_value"] == "12.30"
            assert state.provenance["last_calculation"]["input_count"] == 1
    finally:
        await engine.dispose()


def test_note_formula_evaluator_emits_actual_cell_inputs():
    from app.services import formula_inputs
    from app.services.note_formula_tables import evaluate

    rows = [{"values": [Decimal("1.10")]}, {"values": [Decimal("2.20")]}, {"values": [None]}]
    with formula_inputs.collect() as inputs:
        value, reason = evaluate("SUM(0:1, 0)", rows)
    assert reason is None and value == Decimal("3.30")
    assert [(atom.kind, atom.key, atom.value) for atom in inputs] == [
        ("CELL", "0:0", "1.10"),
        ("CELL", "1:0", "2.20"),
    ]


def test_push_formula_context_emits_selected_tb_and_adjustment_inputs():
    from app.services import formula_inputs
    from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot

    sources = FormulaSources(
        tb=TbAuditedSnapshot(
            tb_data={"1001": {"期末余额": Decimal("10.00")}}, available=True,
        ),
        hall_adj={"1001": {"aje_net": Decimal("1.00")}},
    )
    with formula_inputs.collect() as inputs:
        sources.context_for({
            "tb": "trial_balance_audited",
            "adj": "hall_approved_excluding_workpaper",
        })
    assert {(atom.kind, atom.key, atom.value) for atom in inputs} == {
        ("TB", "1001|期末余额", "10.00"),
        ("ADJ", "1001|aje_net", "1.00"),
    }


@pytest.mark.asyncio
async def test_push_state_applied_attempt_matches_queryable_run_id():
    from datetime import datetime, timezone
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from app.models.formula_push_models import FormulaPushState
    from app.services.formula_push import engine as push_engine
    from app.services.formula_push.results import RunResult
    from app.services.formula_provenance import push_rule_identity

    db_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    project_id = UUID("00000000-0000-0000-0000-000000000020")
    run_id = UUID("00000000-0000-0000-0000-000000000021")
    try:
        async with db_engine.begin() as conn:
            await conn.run_sync(FormulaPushState.__table__.create)
        async with AsyncSession(db_engine) as db:
            rule = SimpleNamespace(rule_id="E1.amount", page_key="wp:E1", stage="source", policy="system", version=1)
            ctx = push_engine._Ctx(
                db=db, project_id=project_id, year=2025, triggered_by=None,
                force=frozenset(), now=datetime(2026, 1, 1, tzinfo=timezone.utc), states={},
                result=RunResult(project_id=project_id, year=2025, trigger="manual"), ruleset_hash="r" * 64,
            )
            ctx.state_writes.append(push_engine._StateWrite(
                addr_id="E1/sheet/item.amount", rule_id="E1.amount", domain="workpaper",
                wp_id=None, note_section=None, formula_value=Decimal("12.30"), current_after=Decimal("12.30"),
                state="auto", record_pushed=True, forced=False,
                definition_identity=push_rule_identity(rule, ctx.ruleset_hash),
                inputs=[InputAtom(kind="TB", key="1001|期末余额", value="12.30")],
                calculation_applied=True,
            ))
            await push_engine._save_states(ctx, run_id)
            final = FinalValueProvenanceV1.model_validate(ctx.states["E1/sheet/item.amount"].provenance)
            assert final.calculation_applied is True
            assert final.applied_attempt is not None
            assert final.applied_attempt.run_id == run_id
            assert final.last_calculation is not None
            assert final.last_calculation.attempt_id == final.applied_attempt.attempt_id
    finally:
        await db_engine.dispose()


def test_push_state_view_redacts_cross_project_inputs():
    from app.services.formula_push.panel import state_view

    identity = definition_identity(
        version=1, layer="system", kind="push_rule", source_id="r1",
        snapshot={"expression": "TB('1001')"},
    )
    attempt = build_attempt(
        domain="push", identity=identity, run_id=RUN_ID,
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), computed_by=None,
        calc_version="push:1",
        inputs=[InputAtom(
            kind="TB", key="子企业 1001", value="12.30",
            source_ref="trial_balance:1001", source_project_id=OTHER_PROJECT,
        )],
        calculated_value=Decimal("12.30"), calculation_status="succeeded",
    )
    provenance = advance_final_value(
        None, value_slot="current", value_state="auto", attempt=attempt,
        calculation_applied=True,
    ).model_dump(mode="json")
    row = SimpleNamespace(
        project_id=UUID(int=1), addr_id="a", rule_id="r1", domain="note",
        wp_id=None, note_section="八、1", state="auto", current_value=12.3,
        last_formula_value=12.3, last_pushed_value=12.3, last_run_id=RUN_ID,
        provenance=provenance, updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    view = state_view(row, allowed_project_ids={UUID(int=1)})
    assert view["last_run_id"] == str(RUN_ID)
    assert view["inputs_redacted"] is True
    atom = view["provenance"]["last_calculation"]["inputs"][0]
    assert atom["value"] is None and atom["source_ref"] is None
