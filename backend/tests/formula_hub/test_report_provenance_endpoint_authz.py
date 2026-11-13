from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
    ReportGenerationRun,
)
from app.routers import reports
from app.services.formula_provenance import (
    advance_final_value,
    build_attempt,
    definition_identity,
)
from tests.authz_world import sqlite_world


@pytest_asyncio.fixture
async def provenance_world(monkeypatch: pytest.MonkeyPatch):
    async with sqlite_world(
        monkeypatch,
        extra_tables=(ReportGenerationRun.__table__, FinancialReport.__table__),
    ) as world:
        yield world


async def _seed(world, actor_id: uuid.UUID) -> FinancialReport:
    now = datetime.now(timezone.utc)
    run = ReportGenerationRun(
        project_id=world.target.id,
        year=2025,
        trigger="full",
        triggered_by=actor_id,
        started_at=now,
        finished_at=now,
        status="succeeded",
        changed_rows=1,
        failed_rows=1,
        error="BS-099：除数为 0",
        calc_version=2,  # 共享运行表（V246）的 calc_version 是整数；信封里的 calc_version 仍是 'report:2'
    )
    world.db.add(run)
    await world.db.flush()
    identity = definition_identity(
        version=1,
        layer="global",
        kind="report_config",
        source_id="cfg-1",
        snapshot={"formula": "TB('1001','期末余额')"},
    )
    attempt = build_attempt(
        domain="report",
        identity=identity,
        run_id=run.id,
        computed_at=now,
        computed_by=actor_id,
        calc_version="report:2",
        inputs=[{"kind": "TB", "key": "1001", "value": Decimal("12.30")}],
        calculated_value=Decimal("12.30"),
        calculation_status="succeeded",
    )
    row = FinancialReport(
        project_id=world.target.id,
        year=2025,
        report_type=FinancialReportType.balance_sheet,
        row_code="BS-001",
        row_name="货币资金",
        current_period_amount=Decimal("12.30"),
        formula_used="TB('1001','期末余额')",
        calc_version=2,
        is_stale=False,
        run_id=run.id,
        provenance=advance_final_value(
            None,
            value_slot="current",
            value_state="auto",
            attempt=attempt,
            calculation_applied=True,
        ).model_dump(mode="json"),
    )
    world.db.add(row)
    await world.db.flush()
    return row


async def test_anonymous_request_is_401(provenance_world):
    world = provenance_world
    path = f"/api/reports/{world.target.id}/2025/balance_sheet/rows/BS-001/provenance"
    async with world.client(reports.router, user=None) as client:
        response = await client.get(path)
    assert response.status_code == 401


async def test_readonly_member_can_read_current_provenance(provenance_world, monkeypatch):
    world = provenance_world
    identity = await world.readonly_member()
    await _seed(world, identity.user.id)

    async def formula_state(*_args, **_kwargs):
        formula = "TB('1001','期末余额')"
        from app.services.formula_provenance import definition_identity
        identity = definition_identity(
            version=1, layer="global", kind="report_config", source_id="cfg-1",
            snapshot={"formula": formula},
        )
        key = (FinancialReportType.balance_sheet.value, "BS-001")
        return {key: formula}, {key: identity.definition_hash}

    monkeypatch.setattr(reports, "load_effective_formula_state", formula_state)
    path = f"/api/reports/{world.target.id}/2025/balance_sheet/rows/BS-001/provenance"
    async with world.client(reports.router, user=identity.user) as client:
        response = await client.get(path)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["row_code"] == "BS-001"
    assert payload["legacy"] is False
    assert payload["envelope"]["calculation_applied"] is True
    # 库里 succeeded + failed_rows=1 ⇒ 对外显示 partial（run_display_status）；失败原因来自共享表的 error 列
    assert payload["run"]["status"] == "partial"
    assert (payload["run"]["failed_rows"], payload["run"]["error_summary"], payload["run"]["calc_version"]) == (
        1, "BS-099：除数为 0", 2)
    assert payload["computed_by_label"] == identity.user.username
