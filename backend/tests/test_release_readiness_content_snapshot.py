"""发布阻断收口：readiness 权威源分流与内容级 snapshot。"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.deliverable_readiness_service import (
    DeliverableReadinessService,
    build_snapshot_digest,
)
from app.services.deliverable_source_digest import content_digest


def _source(digest: str, **extra):
    return {
        "available": True,
        "count": 1,
        "stale_count": 0,
        "detail": {"content_digest": digest, **extra},
    }


def test_snapshot_digest_changes_when_amount_changes_but_count_does_not():
    project_id = uuid4()
    first = {
        "tb": _source(content_digest([{"code": "1001", "amount": Decimal("100.00")}]))
    }
    second = {
        "tb": _source(content_digest([{"code": "1001", "amount": Decimal("101.00")}]))
    }

    before = build_snapshot_digest(project_id, 2025, first)
    after = build_snapshot_digest(project_id, 2025, second)

    assert before["payload"]["sources"]["tb"]["count"] == 1
    assert after["payload"]["sources"]["tb"]["count"] == 1
    assert before["digest"] != after["digest"]


def test_snapshot_payload_includes_dataset_and_successful_run_identity():
    project_id = uuid4()
    run_id = uuid4()
    dataset_id = uuid4()
    result = build_snapshot_digest(
        project_id,
        2025,
        {
            "dataset": _source(
                "a" * 64,
                source_kind="ledger_dataset",
                version_id=str(dataset_id),
            ),
            "formula_push": _source(
                "b" * 64,
                source_kind="consol_push_run",
                run_id=str(run_id),
                run_status="succeeded",
            ),
        },
    )
    assert result["payload"]["sources"]["dataset"]["version_id"] == str(dataset_id)
    assert result["payload"]["sources"]["formula_push"]["run_id"] == str(run_id)
    assert result["payload"]["sources"]["formula_push"]["run_status"] == "succeeded"


@pytest.mark.asyncio
async def test_formula_push_uses_consol_run_for_consolidated(monkeypatch):
    service = DeliverableReadinessService()
    run_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        project_id=uuid4(),
        year=2025,
        status="succeeded",
        trigger_source="manual",
        steps=[{"step": "notes", "status": "succeeded"}],
        warnings=[],
        started_at=None,
        finished_at=None,
    )
    scalars = SimpleNamespace(all=lambda: [run])
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalars)))
    blockers = []

    status = await service._check_formula_push(
        db,
        run.project_id,
        2025,
        blockers,
        report_scope="consolidated",
    )

    assert blockers == []
    assert status.detail["source_kind"] == "consol_push_run"
    assert status.detail["run_id"] == str(run_id)
    sql = str(db.execute.await_args.args[0])
    assert "consol_push_run" in sql
    assert "formula_push_run" not in sql


@pytest.mark.asyncio
async def test_consolidated_notes_use_verified_root_records(monkeypatch):
    service = DeliverableReadinessService()
    project_id = uuid4()
    record = SimpleNamespace(
        id=uuid4(),
        section_id="五-1-1",
        node_key="ROOT:consol",
        data={"headers": ["项目", "期末"], "rows": [["现金", "100"]]},
        is_stale=False,
        cell_state="auto",
        locked_cells=[],
        last_formula_run_id=uuid4(),
        last_formula_value={"cells": [{"row_index": 0, "col_index": 1, "value": 100}]},
    )
    root = SimpleNamespace(
        template_type="soe",
        node_key="ROOT:consol",
        records=[record],
    )
    loader = AsyncMock(return_value=root)
    monkeypatch.setattr(
        "app.services.consol_note_export_adapter.load_root_consol_records",
        loader,
    )
    validate_export = MagicMock(return_value=[SimpleNamespace(note_section="八、1")])
    monkeypatch.setattr(
        "app.services.consol_note_export_adapter.adapt_root_consol_records",
        validate_export,
    )
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("不得查询 DisclosureNote")))
    blockers = []

    status = await service._check_notes(
        db,
        project_id,
        2025,
        blockers,
        report_scope="consolidated",
        template_type="soe",
    )

    assert blockers == []
    assert status.available and status.count == 1 and status.stale_count == 0
    assert status.detail["source_kind"] == "consol_note_data"
    assert status.detail["root_node_key"] == "ROOT:consol"
    assert len(status.detail["content_digest"]) == 64
    loader.assert_awaited_once_with(db, project_id, 2025, template_type="soe")
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_consolidated_notes_stale_root_blocks(monkeypatch):
    from app.services.consol_note_export_adapter import RootConsolNoteRecords

    record = SimpleNamespace(
        id=uuid4(),
        section_id="五-1-1",
        node_key="ROOT:consol",
        data={"headers": ["项目", "期末"], "rows": [["现金", "100"]]},
        is_stale=True,
        cell_state="auto",
        locked_cells=[],
        last_formula_run_id=None,
        last_formula_value=None,
    )
    monkeypatch.setattr(
        "app.services.consol_note_export_adapter.load_root_consol_records",
        AsyncMock(
            return_value=RootConsolNoteRecords(
                template_type="soe",
                node_key="ROOT:consol",
                records=[record],
            )
        ),
    )
    blockers = []
    status = await DeliverableReadinessService()._check_notes(
        SimpleNamespace(),
        uuid4(),
        2025,
        blockers,
        report_scope="consolidated",
        template_type="soe",
    )
    assert status.stale_count == 1
    assert [(item.code, item.evidence["component"]) for item in blockers] == [
        ("stale_source", "consol_disclosure_notes")
    ]


@pytest.mark.asyncio
async def test_same_count_amount_change_blocks_retry_before_step_runner():
    from app.services.export_job_service import ExportJobService, SnapshotConflictError

    project_id = uuid4()
    job_id = uuid4()
    snapshot_id = uuid4()

    def readiness(amount: str):
        return build_snapshot_digest(
            project_id,
            2025,
            {
                "tb": _source(
                    content_digest(
                        [{"account": "1001", "audited_amount": Decimal(amount)}]
                    )
                )
            },
        )

    before = readiness("100.00")
    after = readiness("101.00")
    assert before["payload"]["sources"]["tb"]["count"] == 1
    assert after["payload"]["sources"]["tb"]["count"] == 1

    db_result = SimpleNamespace(
        scalar_one_or_none=lambda: SimpleNamespace(digest=before["digest"])
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=db_result))
    service = ExportJobService(db)
    service.get_job = AsyncMock(
        return_value=SimpleNamespace(
            id=job_id,
            kind="deliverable_trio",
            snapshot_id=snapshot_id,
        )
    )
    runner = SimpleNamespace(run_step=AsyncMock())

    with pytest.raises(SnapshotConflictError):
        await service.retry_failed_trio(
            job_id,
            step_runner=runner,
            current_snapshot_digest=after["digest"],
        )
    runner.run_step.assert_not_awaited()


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


@pytest.mark.asyncio
async def test_trial_balance_query_digest_tracks_amount_with_same_row_count():
    service = DeliverableReadinessService()
    project_id = uuid4()

    def row(amount: str):
        return {
            "id": uuid4(),
            "company_code": "001",
            "standard_account_code": "1001",
            "account_name": "库存现金",
            "account_category": "asset",
            "unadjusted_amount": Decimal(amount),
            "rje_adjustment": Decimal("0"),
            "aje_adjustment": Decimal("0"),
            "audited_amount": Decimal(amount),
            "wp_adjustment": Decimal("0"),
            "wp_publish_base": None,
            "opening_balance": Decimal("80"),
            "currency_code": "CNY",
        }

    stable_id = uuid4()
    first_row = row("100.00")
    first_row["id"] = stable_id
    second_row = row("101.00")
    second_row["id"] = stable_id
    first = await service._check_trial_balance(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([first_row]))),
        project_id,
        2025,
        [],
    )
    second = await service._check_trial_balance(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([second_row]))),
        project_id,
        2025,
        [],
    )

    assert first.count == second.count == 1
    assert first.detail["content_digest"] != second.detail["content_digest"]


def test_display_preferences_json_constraint_is_pg_only_but_default_is_portable():
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from app.models.user_display_preferences import UserDisplayPreferences

    pg_sql = str(
        CreateTable(UserDisplayPreferences.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    sqlite_sql = str(
        CreateTable(UserDisplayPreferences.__table__).compile(
            dialect=sqlite.dialect()
        )
    )
    assert "jsonb_typeof(fixed_columns) = 'object'" in pg_sql
    assert "jsonb_typeof" not in sqlite_sql
    assert "::jsonb" not in sqlite_sql


@pytest.mark.asyncio
async def test_adjustment_digest_tracks_amount_with_same_group_count(monkeypatch):
    """分录组数量不变时，任一行金额变化仍必须推进 trio snapshot。"""
    service = DeliverableReadinessService()
    project_id = uuid4()
    stable_id = uuid4()

    async def count_groups(_db, _project_id, _year, *, review_statuses=None):
        return 0 if review_statuses is not None else 1

    monkeypatch.setattr(
        "app.services.wp_adjustment_helpers.count_adjustment_groups",
        count_groups,
    )

    def row(amount: str):
        return SimpleNamespace(
            id=stable_id,
            company_code="001",
            adjustment_no="AJE-001",
            adjustment_type="audit",
            description="调整应收账款",
            account_code="1122",
            account_name="应收账款",
            debit_amount=Decimal(amount),
            credit_amount=Decimal("0"),
            entry_group_id=uuid4(),
            review_status="approved",
            reviewer_id=uuid4(),
            rejection_reason=None,
            passed_reason="复核通过",
            origin="manual",
            source_ref=None,
        )

    first_row = row("100.00")
    second_row = row("101.00")
    second_row.entry_group_id = first_row.entry_group_id
    second_row.reviewer_id = first_row.reviewer_id

    first = await service._check_adjustments(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([first_row]))),
        project_id,
        2025,
        [],
        [],
    )
    second = await service._check_adjustments(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([second_row]))),
        project_id,
        2025,
        [],
        [],
    )

    assert first.count == second.count == 1
    assert first.detail["line_count"] == second.detail["line_count"] == 1
    assert first.detail["content_digest"] != second.detail["content_digest"]


@pytest.mark.asyncio
async def test_report_digest_tracks_amount_with_same_row_count(monkeypatch):
    """报表行数和 calc_version 不变时，金额变化仍必须推进 trio snapshot。"""
    service = DeliverableReadinessService()
    project_id = uuid4()
    stable_id = uuid4()

    async def count_summary(_db, _project_id, _year):
        return SimpleNamespace(total=1, stale=0, calc_error=0, blank=0)

    monkeypatch.setattr("app.services.report_freshness.count_summary", count_summary)

    def row(amount: str):
        return SimpleNamespace(
            id=stable_id,
            report_type="balance_sheet",
            row_code="A001",
            row_name="货币资金",
            current_period_amount=Decimal(amount),
            prior_period_amount=Decimal("80.00"),
            formula_used="TB('1001')",
            source_accounts=["1001"],
            indent_level=0,
            is_total_row=False,
            is_stale=False,
            blank_reason=None,
            calc_version=3,
            calc_error=None,
        )

    first = await service._check_reports(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([row("100.00")]))),
        project_id,
        2025,
        [],
    )
    second = await service._check_reports(
        SimpleNamespace(execute=AsyncMock(return_value=_RowsResult([row("101.00")]))),
        project_id,
        2025,
        [],
    )

    assert first.count == second.count == 1
    assert first.detail["version_id"] == second.detail["version_id"] == "calc:3"
    assert first.detail["content_digest"] != second.detail["content_digest"]


def test_readiness_service_does_not_shadow_shared_content_digest_sources():
    """调整与报表不得再在子类复制一份无 content_digest 的旧实现。"""
    assert "_check_adjustments" not in DeliverableReadinessService.__dict__
    assert "_check_reports" not in DeliverableReadinessService.__dict__
