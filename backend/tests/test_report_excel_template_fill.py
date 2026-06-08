"""Integration tests for ReportExcelExporter cell_mapping / inline-placeholder fill.

Task 20 (audit-report-template-integration): verifies the double-track fill
(design §6) against the real POC template ``soe_standalone.xlsx``:

- Inline ``{{row:BS-xxx:current/prior}}`` placeholders are replaced by audited
  values at their actual coordinates (C6/D6 …), NOT by row order.
- Header placeholders (``{{company_full_name}}`` …) are substituted in-text.
- Formula/total rows (``=SUM`` at C31/D31/C57/D57) are NOT overwritten.
- ``fill_empty_as`` honored for row_codes with no data.

If the POC xlsx is absent, a synthetic workbook with the same inline +
SUM pattern is constructed and the same behavior is asserted.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project
from app.models.report_models import FinancialReport, FinancialReportType
from app.services.report_excel_exporter import ReportExcelExporter
from app.services.template_manifest_loader import resolve_template_base_dir

_POC_PATH = (
    resolve_template_base_dir()
    / "financial_statements"
    / "soe_standalone.xlsx"
)
_BS_SHEET = "1,2-资产负债表(企财01表）"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_async_session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def soe_project(db_session: AsyncSession):
    project = Project(
        id=uuid.uuid4(),
        name="致同测试国企有限公司",
        client_name="致同测试国企有限公司",
        template_type="soe",
        report_scope="standalone",
    )
    db_session.add(project)
    await db_session.flush()
    return project


@pytest_asyncio.fixture
async def bs_rows(db_session: AsyncSession, soe_project: Project):
    """BS-002 货币资金 has values; BS-003 left empty (fill_empty_as=blank)."""
    now = datetime.now(timezone.utc)
    rows = [
        FinancialReport(
            id=uuid.uuid4(),
            project_id=soe_project.id,
            year=2024,
            report_type=FinancialReportType.balance_sheet,
            row_code="BS-002",
            row_name="货币资金",
            current_period_amount=Decimal("1234567.89"),
            prior_period_amount=Decimal("987654.32"),
            indent_level=1,
            is_total_row=False,
            generated_at=now,
        ),
        FinancialReport(
            id=uuid.uuid4(),
            project_id=soe_project.id,
            year=2024,
            report_type=FinancialReportType.balance_sheet,
            row_code="BS-008",
            row_name="应收账款",
            current_period_amount=Decimal("-50000.00"),
            prior_period_amount=Decimal("60000.00"),
            indent_level=1,
            is_total_row=False,
            generated_at=now,
        ),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.flush()
    return rows


@pytest.mark.skipif(not _POC_PATH.is_file(), reason="POC template absent in checkout")
@pytest.mark.asyncio
async def test_poc_template_inline_fill(db_session, soe_project, bs_rows):
    """Real POC template: inline placeholders filled at C6/D6, SUM preserved."""
    exporter = ReportExcelExporter(db_session)
    output = await exporter.export(
        project_id=soe_project.id,
        year=2024,
        mode="audited",
        report_types=["balance_sheet"],
        include_prior_year=True,
    )
    wb = load_workbook(output)
    assert _BS_SHEET in wb.sheetnames
    ws = wb[_BS_SHEET]

    # BS-002 (row 6): audited values replace the {{row:...}} placeholders
    assert ws["C6"].value == pytest.approx(1234567.89)
    assert ws["D6"].value == pytest.approx(987654.32)

    # BS-008 (row 12): negative current value
    assert ws["C12"].value == pytest.approx(-50000.00)
    assert ws["D12"].value == pytest.approx(60000.00)

    # BS-003 (row 7): no data + fill_empty_as=blank → cleared, NOT a placeholder
    assert ws["C7"].value in (None, "")
    assert "{{" not in str(ws["C7"].value or "")

    # Formula/total rows must NOT be overwritten
    for coord in ("C31", "D31", "C56", "D56", "C57", "D57"):
        val = ws[coord].value
        assert isinstance(val, str) and val.startswith("="), (
            f"{coord} formula was overwritten: {val!r}"
        )

    # Header placeholder replaced (A3='编制单位：{{company_full_name}}')
    assert "致同测试国企有限公司" in str(ws["A3"].value)
    assert "{{" not in str(ws["A3"].value)
    # A2 period_end_date
    assert "2024年12月31日" in str(ws["A2"].value)


@pytest.mark.asyncio
async def test_synthetic_inline_fill(db_session, soe_project, bs_rows, tmp_path, monkeypatch):
    """Synthetic template with same inline + SUM pattern (path-independent guard)."""
    # Build a synthetic template mirroring the POC layout
    wb = Workbook()
    ws = wb.active
    ws.title = _BS_SHEET
    ws["A2"] = "{{period_end_date}}"
    ws["A3"] = "编制单位：{{company_full_name}}"
    ws["A6"] = "货币资金"
    ws["C6"] = "{{row:BS-002:current}}"
    ws["D6"] = "{{row:BS-002:prior}}"
    ws["A7"] = "应收账款"
    ws["C7"] = "{{row:BS-008:current}}"
    ws["D7"] = "{{row:BS-008:prior}}"
    ws["A8"] = "空行"
    ws["C8"] = "{{row:BS-003:current}}"  # no data → blank
    ws["A9"] = "合计"
    ws["C9"] = "=SUM(C6:C8)"
    ws["D9"] = "=SUM(D6:D8)"
    synth = tmp_path / "synthetic.xlsx"
    wb.save(synth)

    # Force exporter to load the synthetic template
    def _fake_load(self, template_key):
        return load_workbook(str(synth))

    monkeypatch.setattr(ReportExcelExporter, "_load_template", _fake_load)

    exporter = ReportExcelExporter(db_session)
    output = await exporter.export(
        project_id=soe_project.id,
        year=2024,
        mode="audited",
        report_types=["balance_sheet"],
        include_prior_year=True,
    )
    out_wb = load_workbook(output)
    out = out_wb[_BS_SHEET]

    assert out["C6"].value == pytest.approx(1234567.89)
    assert out["D6"].value == pytest.approx(987654.32)
    assert out["C7"].value == pytest.approx(-50000.00)
    # SUM formula preserved
    assert str(out["C9"].value).startswith("=SUM")
    assert str(out["D9"].value).startswith("=SUM")
    # Header substituted
    assert "致同测试国企有限公司" in str(out["A3"].value)
    assert "2024年12月31日" in str(out["A2"].value)
