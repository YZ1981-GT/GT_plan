from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa


class _Result:
    def __init__(self, value=None, rows=()):
        self.value = value
        self.rows = list(rows)

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value

    def first(self):
        return self.value

    def all(self):
        return list(self.rows)

    def fetchall(self):
        return list(self.rows)


class _Db:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.mark.asyncio
async def test_business_pattern_reads_aux_balance_and_ledger(monkeypatch):
    from app.routers.wp_business_pattern import _analyze_payment_patterns

    project_id = uuid4()
    active_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", active_filter)
    db = _Db([_Result(rows=[SimpleNamespace(aux_name="甲客户", aux_code="C1", txn_count=2)])])

    patterns = await _analyze_payment_patterns(db, project_id, None, year=2025)

    assert [(item.customer, item.payment_cycle_days) for item in patterns] == [("甲客户", 30)]
    assert active_filter.await_count == 2
    assert all(call.args[3] == 2025 for call in active_filter.await_args_list)
    sql = str(db.statements[0])
    assert "tb_aux_balance" in sql
    assert "tb_aux_ledger" in sql
    assert "tb_ledger" not in sql


@pytest.mark.asyncio
async def test_business_pattern_query_failure_is_identifiable(monkeypatch):
    from fastapi import HTTPException

    from app.routers.wp_business_pattern import _analyze_payment_patterns

    active_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", active_filter)
    db = _Db([RuntimeError("database unavailable")])

    with pytest.raises(HTTPException) as caught:
        await _analyze_payment_patterns(db, uuid4(), None, year=2025)

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == "BUSINESS_PATTERN_QUERY_FAILED"
    assert "示例客户" not in str(caught.value.detail)


@pytest.mark.asyncio
async def test_formula_config_coverage_uses_effective_project_scope(monkeypatch):
    from app.services import report_config_service
    from app.services.formula_settings import effective_report
    from app.services.formula_health_service import _config_coverage

    project_id = uuid4()

    async def standard(_db, _project_id):
        return "enterprise"

    async def load(_db, *, standard, project_id, report_type=None):
        assert standard == "enterprise"
        assert project_id == project_id_for_test
        assert report_type is None
        return [
            SimpleNamespace(formula="TB('1001','期末余额')"),
            SimpleNamespace(formula=None),
            SimpleNamespace(formula="  "),
        ]

    project_id_for_test = project_id
    monkeypatch.setattr(
        report_config_service.ReportConfigService,
        "resolve_applicable_standard",
        staticmethod(standard),
    )
    monkeypatch.setattr(effective_report, "load_effective_report_configs", load)

    result = await _config_coverage(object(), project_id, 2025)

    assert result == {
        "available": True,
        "total_rows": 3,
        "with_formula": 1,
        "without_formula": 2,
        "coverage_rate": 33.3,
    }


@pytest.mark.asyncio
async def test_formula_config_coverage_failure_is_not_zero_percent(monkeypatch):
    from app.services import report_config_service
    from app.services.formula_settings import effective_report
    from app.services.formula_health_service import _config_coverage

    async def standard(_db, _project_id):
        return "enterprise"

    async def fail(*args, **kwargs):
        raise RuntimeError("report config unavailable")

    monkeypatch.setattr(
        report_config_service.ReportConfigService,
        "resolve_applicable_standard",
        staticmethod(standard),
    )
    monkeypatch.setattr(effective_report, "load_effective_report_configs", fail)

    result = await _config_coverage(object(), uuid4(), 2025)

    assert result["available"] is False
    assert result["error"] == "FORMULA_CONFIG_COVERAGE_UNAVAILABLE"
    assert result["coverage_rate"] is None


@pytest.mark.asyncio
async def test_note_ai_loads_workpaper_parsed_data_through_index():
    from app.services.note_ai_assistant_service import NoteAIAssistantService

    project_id = uuid4()
    parsed = {"summary": "底稿摘要"}
    db = _Db([_Result(value=parsed)])

    loaded = await NoteAIAssistantService(db)._load_workpaper_data(
        project_id, 2025, "D2-1"
    )

    assert loaded == parsed
    sql = str(db.statements[0])
    assert "working_paper.parsed_data" in sql
    assert "JOIN wp_index" in sql
    assert "working_paper.wp_index_id = wp_index.id" in sql
    assert "wp_index.parsed_data" not in sql
    assert "working_paper.is_deleted" in sql
    assert "wp_index.is_deleted" in sql
    assert "projects.audit_year" in sql


@pytest.mark.asyncio
async def test_note_ai_context_query_failure_does_not_become_empty_context():
    from app.services.note_ai_assistant_service import NoteAIAssistantService

    db = _Db([RuntimeError("database unavailable")])

    with pytest.raises(RuntimeError, match="底稿 AI 上下文查询失败"):
        await NoteAIAssistantService(db)._load_workpaper_data(uuid4(), 2025, "D2-1")


@pytest.mark.asyncio
async def test_note_ai_auxiliary_reader_uses_real_balance_table(monkeypatch):
    from app.services.note_ai_assistant_service import NoteAIAssistantService

    active_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", active_filter)
    row = SimpleNamespace(
        _mapping={"aux_type": "客户", "aux_code": "C1", "aux_name": "甲客户"}
    )
    db = _Db([_Result(rows=[row])])

    result = await NoteAIAssistantService(db)._query_aux_balance(
        uuid4(), 2025, ["1122"]
    )

    assert result == [{"aux_type": "客户", "aux_code": "C1", "aux_name": "甲客户"}]
    sql = str(db.statements[0])
    assert "tb_aux_balance" in sql
    assert "tb_balance" not in sql


@pytest.mark.asyncio
async def test_prefill_header_uses_client_name_audit_year_and_username(tmp_path):
    import openpyxl

    from app.services.prefill_engine import fill_header_cells

    path = tmp_path / "D2-1.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "D2-1"
    workbook.save(path)
    workbook.close()

    project_id = uuid4()
    wp_id = uuid4()
    index_id = uuid4()
    user_id = uuid4()
    wp = SimpleNamespace(
        id=wp_id,
        project_id=project_id,
        wp_index_id=index_id,
        file_path=str(path),
        created_by=user_id,
        created_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    metadata = SimpleNamespace(
        header_cells={
            "default": {
                "company_name": {"cell": "A1"},
                "audit_period": {"cell": "B1"},
                "preparer": {"cell": "C1"},
            }
        }
    )
    db = _Db(
        [
            _Result(value=wp),
            _Result(value=("D2-1", "应收账款审定表")),
            _Result(value=metadata),
            _Result(value=("auditor01",)),
        ]
    )

    result = await fill_header_cells(
        db,
        wp_id,
        project=SimpleNamespace(client_name="真实客户", audit_year=2025),
    )

    assert result["status"] == "ok"
    saved = openpyxl.load_workbook(path, data_only=False)
    sheet = saved["D2-1"]
    assert sheet["A1"].value == "真实客户"
    assert sheet["B1"].value == "2025"
    assert sheet["C1"].value == "auditor01 2025-01-02"
    assert "full_name" not in str(db.statements[-1])
    saved.close()


@pytest.mark.asyncio
async def test_procedure_control_deficiency_uses_status_not_soft_delete():
    from app.services.procedure_table_auto_service import ProcedureTableService

    db = _Db([_Result(value=3)])
    item = {
        "auto_data_source": "control_deficiency_count",
        "applicable_default": "yes",
    }

    result = await ProcedureTableService(db)._resolve_auto_values(
        uuid4(), 2025, item, "C", "C1A"
    )

    assert result["summary"] == "已识别3项内控缺陷"
    statement = db.statements[0]
    sql = str(statement)
    assert "issue_tickets.status" in sql
    params = statement.compile().params
    assert "rejected" in str(params)
    assert "closed" in str(params)
    assert "issue_tickets.is_deleted" not in sql


@pytest.mark.asyncio
async def test_note_ai_tb_reader_uses_trial_balance_authoritative_amount(monkeypatch):
    from app.services.note_ai_assistant_service import NoteAIAssistantService

    active_filter = AsyncMock(return_value=sa.true())
    monkeypatch.setattr("app.services.dataset_query.get_active_filter", active_filter)
    db = _Db([_Result(value=12.5)])

    value = await NoteAIAssistantService(db)._get_tb_value(
        uuid4(), 2025, ["1122"]
    )

    assert value == 12.5
    sql = str(db.statements[0])
    assert "trial_balance.audited_amount" in sql
    assert "tb_balance" not in sql


def test_business_pattern_endpoint_requires_project_read_access():
    import inspect

    from app.routers.wp_business_pattern import business_pattern_analysis

    source = inspect.getsource(business_pattern_analysis)
    assert 'Depends(require_project_access("readonly"))' in source
    assert "Depends(get_current_user)" not in source
