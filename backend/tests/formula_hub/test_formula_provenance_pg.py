from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import ProjectStatus, ProjectType
from app.models.core import Project
from app.models.formula_push_models import FormulaPushRun, FormulaPushState
from app.models.note_formula_models import NoteFormulaRun
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    ReportConfig,
    ReportGenerationRun,
)
from app.services.formula_provenance import InputAtom, push_rule_identity
from app.services.formula_push import engine as push_engine
from app.services.formula_push.results import RunResult
from app.services.note_formula_generator import execute_note_formulas
from app.services.report_engine import ReportEngine

pytestmark = pytest.mark.pg_only
YEAR = 2025


async def _project(db, label: str) -> Project:
    project = Project(
        id=uuid.uuid4(), name=f"【测试】S5-{label}-{uuid.uuid4().hex[:8]}",
        client_name="【测试】来源信封", project_type=ProjectType.annual,
        status=ProjectStatus.execution, template_type="soe", report_scope="standalone",
        audit_year=YEAR, is_deleted=False,
    )
    db.add(project)
    await db.flush()
    return project


async def test_v236_v237_v238_schema_contract_pg(pg_tx):
    columns = (await pg_tx.execute(sa.text(
        "SELECT table_name, column_name, data_type, is_nullable "
        "FROM information_schema.columns WHERE table_schema='public' AND "
        "((table_name='financial_report' AND column_name IN ('run_id','provenance')) OR "
        "(table_name='formula_push_state' AND column_name='provenance')) ORDER BY 1,2"
    ))).all()
    assert [tuple(row) for row in columns] == [
        ("financial_report", "provenance", "jsonb", "YES"),
        ("financial_report", "run_id", "uuid", "YES"),
        ("formula_push_state", "provenance", "jsonb", "YES"),
    ]
    assert (await pg_tx.execute(sa.text(
        "SELECT to_regclass('public.report_generation_run')::text, "
        "to_regclass('public.note_formula_run')::text"
    ))).one() == ("report_generation_run", "note_formula_run")
    constraints = set((await pg_tx.execute(sa.text(
        "SELECT conname FROM pg_constraint WHERE conname IN "
        "('fk_financial_report_run','ck_report_generation_run_status','ck_note_formula_run_status')"
    ))).scalars())
    assert constraints == {
        "fk_financial_report_run", "ck_report_generation_run_status", "ck_note_formula_run_status",
    }


async def test_report_full_run_persists_success_and_failed_attempts_pg(pg_tx):
    project = await _project(pg_tx, "report")
    standard = f"project:{project.id}"
    pg_tx.add_all([
        ReportConfig(
            report_type=FinancialReportType.balance_sheet, row_number=1,
            row_code="FPE-PG-OK", row_name="成功行",
            formula="TB('1001','期末余额')", formula_category="auto_calc",
            applicable_standard=standard, is_deleted=False,
        ),
        ReportConfig(
            report_type=FinancialReportType.balance_sheet, row_number=2,
            row_code="FPE-PG-FAIL", row_name="失败行", formula="1/0",
            formula_category="auto_calc", applicable_standard=standard, is_deleted=False,
        ),
        TrialBalance(
            project_id=project.id, year=YEAR, company_code="001",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset, audited_amount=Decimal("12.30"),
            unadjusted_amount=Decimal("12.30"), opening_balance=Decimal("1.00"), is_deleted=False,
        ),
        FinancialReport(
            project_id=project.id, year=YEAR,
            report_type=FinancialReportType.balance_sheet,
            row_code="FPE-PG-FAIL", row_name="失败行",
            current_period_amount=Decimal("77.00"), formula_used="旧公式",
            is_stale=True, calc_version=2, is_deleted=False,
        ),
    ])
    await pg_tx.flush()

    await ReportEngine(pg_tx).generate_all_reports(
        project.id, YEAR, applicable_standard=standard,
        skip_recalc=True, publish_events=False,
    )
    await pg_tx.flush()
    runs = list((await pg_tx.execute(sa.select(ReportGenerationRun).where(
        ReportGenerationRun.project_id == project.id,
    ))).scalars())
    from app.services.report_freshness import CALC_VERSION
    from app.services.report_provenance import run_display_status
    assert len(runs) == 1 and (runs[0].status, run_display_status(runs[0])) == ("succeeded", "partial")
    assert runs[0].failed_rows == 1 and runs[0].calc_version == CALC_VERSION
    rows = {row.row_code: row for row in (await pg_tx.execute(sa.select(FinancialReport).where(
        FinancialReport.project_id == project.id,
    ))).scalars()}
    success, failed = rows["FPE-PG-OK"], rows["FPE-PG-FAIL"]
    assert success.current_period_amount == Decimal("12.30")
    assert success.run_id == runs[0].id
    assert success.provenance["applied_attempt"]["run_id"] == str(runs[0].id)
    assert {item["kind"] for item in success.provenance["last_calculation"]["inputs"]} == {"TB"}
    assert failed.current_period_amount == Decimal("77.00")
    assert failed.run_id is None
    assert failed.provenance["calculation_applied"] is False
    assert failed.provenance["last_calculation"]["calculation_status"] == "failed"


async def test_note_run_and_unapplied_manual_provenance_pg(pg_tx):
    project = await _project(pg_tx, "note")
    table = {
        "headers": ["项目", "金额"],
        "rows": [
            {"label": "子项", "values": [10.0]},
            {"label": "合计", "values": [99.0], "_cell_modes": {"0": "manual"}},
        ],
        "_formulas": {
            "1:0": {"type": "vertical_sum", "expression": "SUM(0:0, 0)", "category": "auto_calc"},
        },
    }
    note = DisclosureNote(
        project_id=project.id, year=YEAR, note_section="八、FPE",
        section_title="来源测试", content_type=ContentType.table,
        table_data=table, is_deleted=False,
    )
    pg_tx.add(note)
    await pg_tx.flush()
    result = await execute_note_formulas(
        pg_tx, project.id, YEAR, note.note_section, trigger="system_test",
    )
    await pg_tx.flush()
    run = await pg_tx.get(NoteFormulaRun, uuid.UUID(result["run_id"]))
    assert run is not None and run.status == "succeeded"
    await pg_tx.refresh(note)
    final = note.table_data["_formula_provenance"]["note:八、FPE!1:0"]
    assert note.table_data["rows"][1]["values"][0] == 99.0
    assert final["value_state"] == "manual"
    assert final["calculation_applied"] is False
    assert final["last_calculation"]["calculated_value"] == "10.00"
    assert {item["kind"] for item in final["last_calculation"]["inputs"]} == {"CELL"}


async def test_push_state_keeps_formula_attempt_when_target_does_not_adopt_pg(pg_tx):
    project = await _project(pg_tx, "push")
    run = FormulaPushRun(
        project_id=project.id, year=YEAR, trigger_source="manual",
        status="running", detail={}, started_at=datetime.now(timezone.utc),
    )
    pg_tx.add(run)
    await pg_tx.flush()
    rule = SimpleNamespace(
        rule_id="FPE.push", page_key="workpaper:E1", stage="source", policy="editable",
        target={}, source={}, triggers=("manual",), version=1, status="active",
    )
    ctx = push_engine._Ctx(
        db=pg_tx, project_id=project.id, year=YEAR, triggered_by=None,
        force=frozenset(), now=datetime.now(timezone.utc), states={},
        result=RunResult(project_id=project.id, year=YEAR, trigger="manual"),
        ruleset_hash="a" * 64,
    )
    ctx.state_writes.append(push_engine._StateWrite(
        addr_id="E1/E1-1/FPE.amount", rule_id=rule.rule_id, domain="workpaper",
        wp_id=None, note_section=None, formula_value=Decimal("12.30"),
        current_after=Decimal("99.00"), state="pending_confirm",
        record_pushed=False, forced=False,
        definition_identity=push_rule_identity(rule, ctx.ruleset_hash),
        inputs=[InputAtom(kind="TB", key="1001|期末余额", value=Decimal("12.30"))],
        calculation_applied=False,
    ))
    await push_engine._save_states(ctx, run.id)
    await pg_tx.flush()
    state = (await pg_tx.execute(sa.select(FormulaPushState).where(
        FormulaPushState.project_id == project.id,
    ))).scalar_one()
    assert state.last_run_id == run.id
    assert state.current_value == 99.0
    assert state.provenance["calculation_applied"] is False
    assert state.provenance["applied_attempt"] is None
    assert state.provenance["last_calculation"]["calculated_value"] == "12.30"
