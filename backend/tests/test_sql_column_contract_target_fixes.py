"""目标 SQL/ORM 列契约修复的最小行为回归测试。"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self


class _Db:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.results.pop(0)


def test_ocr_confirmation_projection_keeps_legacy_response_keys():
    from app.routers.ocr_governance_router import _confirmation_to_dict

    confirmation = SimpleNamespace(
        id=uuid4(),
        ocr_result_id=uuid4(),
        field_key="amount",
        decision="accepted",
        original_value="100",
        confirmed_value="100",
        confirmed_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )

    result = _confirmation_to_dict(confirmation)

    assert result["result_id"] == str(confirmation.ocr_result_id)
    assert result["field_name"] == "amount"
    assert result["created_at"] == confirmation.confirmed_at.isoformat()
    assert result["actor_type"] == "user"


def test_log_routes_use_action_type_column():
    from app.routers import wp_batch_router, workhours

    edit_time_source = inspect.getsource(workhours.edit_time_suggest)
    batch_edit_time_source = inspect.getsource(wp_batch_router.get_edit_time)

    assert "Log.action_type" in edit_time_source
    assert "Log.action.in_" not in edit_time_source
    assert "Log.action_type" in batch_edit_time_source
    assert "Log.action ==" not in batch_edit_time_source


@pytest.mark.asyncio
async def test_triple_format_adapters_use_real_columns_and_legacy_cells():
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry
    from app.models.report_models import FinancialReport
    from app.services.triple_format_adapter import (
        AdjustmentSummaryAdapter,
        FinancialReportAdapter,
    )

    report_row = SimpleNamespace(
        row_name="货币资金",
        row_code="BS-001",
        current_period_amount=Decimal("12.50"),
        prior_period_amount=Decimal("10.00"),
        indent_level=0,
        is_total_row=False,
        formula_used=None,
    )
    report_db = _Db([_Rows([report_row])])
    report = await FinancialReportAdapter.report_to_structure(
        report_db, uuid4(), 2025, "BS"
    )
    report_order = report_db.statements[0]._order_by_clauses

    assert report["sheets"][0]["cells"]["1:2"]["value"] == 12.5
    assert report["sheets"][0]["cells"]["1:3"]["value"] == 10.0
    assert list(report_order)[0].compare(FinancialReport.row_code.__clause_element__())
    assert "row_order" not in str(report_db.statements[0])

    adjustment = SimpleNamespace(
        adjustment_no="AJE-001",
        description="测试调整",
    )
    entry = SimpleNamespace(
        account_code="1001",
        account_name="库存现金",
        debit_amount=Decimal("5.00"),
        credit_amount=None,
        id=uuid4(),
    )
    adjustment_db = _Db([_Rows([(adjustment, entry)])])
    structure = await AdjustmentSummaryAdapter.summary_to_structure(
        adjustment_db, uuid4(), 2025, "aje"
    )
    statement_text = str(adjustment_db.statements[0])

    assert structure["sheets"][0]["cells"]["1:0"]["value"] == "AJE-001"
    assert "adjustment_type" in statement_text
    assert "adjustment_no" in statement_text
    assert "entry_type" not in statement_text
    assert "entry_number" not in statement_text
    assert "adjustment_type" in Adjustment.__table__.c
    assert "id" in AdjustmentEntry.__table__.c


@pytest.mark.asyncio
async def test_auto_collector_reads_ts_and_workpaper_id_without_empty_fallback():
    from app.services.work_hour_auto_collector import WorkHourAutoCollector

    user_id = uuid4()
    project_id = uuid4()
    workpaper_id = uuid4()
    timestamp = datetime(2025, 1, 2, 9, 30, tzinfo=timezone.utc)
    db = _Db(
        [
            _Rows(
                [
                    SimpleNamespace(
                        object_type="working_paper",
                        object_id=workpaper_id,
                        action_type="workpaper_save",
                        ts=timestamp,
                        payload={"project_id": str(project_id)},
                    )
                ]
            ),
            _Rows([SimpleNamespace(workpaper_id=workpaper_id, created_at=timestamp)]),
            _Rows([SimpleNamespace(wp_id=workpaper_id, project_id=project_id)]),
        ]
    )
    collector = WorkHourAutoCollector(db)

    audit_activities = await collector._collect_audit_log(
        user_id, timestamp.date(), timestamp.date()
    )
    extraction_activities = await collector._collect_extraction_log(
        user_id, timestamp.date(), timestamp.date()
    )

    assert audit_activities[0]["timestamp"] == timestamp
    assert extraction_activities[0]["project_id"] == str(project_id)
    assert "created_at" not in str(db.statements[0].selected_columns)
    assert "workpaper_id" in str(db.statements[1])


@pytest.mark.asyncio
async def test_fill_tasks_scope_through_working_paper_project():
    from app.services.workpaper_fill_service import WorkpaperFillService

    project_id = uuid4()
    task = SimpleNamespace(id=uuid4())
    db = _Db([_Rows([task])])

    result = await WorkpaperFillService(db).list_tasks(project_id)

    statement_text = str(db.statements[0])
    assert result == [task]
    assert "working_paper" in statement_text
    assert "project_id" in statement_text
    assert "ai_workpaper_tasks.project_id" not in statement_text


def test_partner_qc_readiness_joins_working_paper_for_project_scope():
    from app.services.partner_service import SignReadinessService

    source = inspect.getsource(SignReadinessService.check_workpaper_readiness)

    assert "WpQcResult.working_paper_id == WorkingPaper.id" in source
    assert "WorkingPaper.project_id == project_id" in source
    assert "WpQcResult.project_id" not in source
    assert "max(WpQcResult.check_timestamp)" in source
    assert "func.distinct(WpQcResult.working_paper_id)" in source
