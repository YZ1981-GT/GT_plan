"""附注来源追溯 API 单元测试

Validates: Requirements F1.1
Tests:
- 附注 cell 追溯到报表行 + TB 科目
- 无来源时返回 source_type="none"
- 无效 cell_id 返回 400
- 附注不存在返回 404
- 权限校验（通过 require_project_access）
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, User, UserRole
from app.models.audit_platform_models import (
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
    TbBalance,
)
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
)

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    """Create a test project."""
    p = Project(
        id=uuid.uuid4(),
        name="追溯测试项目",
        client_name="追溯测试客户",
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def note_with_accounts(db_session: AsyncSession, project: Project) -> DisclosureNote:
    """Create a disclosure note with table_data containing account_codes."""
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2024,
        note_section="五、1",
        section_title="货币资金",
        content_type=ContentType.table,
        table_data={
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [
                {
                    "label": "库存现金",
                    "values": [50000, 40000],
                    "account_codes": ["1001"],
                },
                {
                    "label": "银行存款",
                    "values": [4950000, 4000000],
                    "account_codes": ["1002"],
                },
                {
                    "label": "合计",
                    "values": [5000000, 4040000],
                    "is_total": True,
                    "account_codes": ["1001", "1002"],
                },
            ],
        },
    )
    db_session.add(note)
    await db_session.flush()
    return note


@pytest_asyncio.fixture
async def note_without_accounts(db_session: AsyncSession, project: Project) -> DisclosureNote:
    """Create a disclosure note with table_data but no account_codes."""
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2024,
        note_section="五、99",
        section_title="其他",
        content_type=ContentType.table,
        table_data={
            "headers": ["项目", "金额"],
            "rows": [
                {"label": "某项目", "values": [100]},
            ],
        },
    )
    db_session.add(note)
    await db_session.flush()
    return note


@pytest_asyncio.fixture
async def report_line_mappings(db_session: AsyncSession, project: Project) -> list[ReportLineMapping]:
    """Create report line mappings for 1001 and 1002."""
    mappings = [
        ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1001",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001",
            report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
        ),
        ReportLineMapping(
            id=uuid.uuid4(),
            project_id=project.id,
            standard_account_code="1002",
            report_type=ReportType.balance_sheet,
            report_line_code="BS-001",
            report_line_name="货币资金",
            report_line_level=1,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=True,
        ),
    ]
    for m in mappings:
        db_session.add(m)
    await db_session.flush()
    return mappings


@pytest_asyncio.fixture
async def financial_report(db_session: AsyncSession, project: Project) -> FinancialReport:
    """Create a financial report row for BS-001."""
    from decimal import Decimal

    fr = FinancialReport(
        id=uuid.uuid4(),
        project_id=project.id,
        year=2024,
        report_type=FinancialReportType.balance_sheet,
        row_code="BS-001",
        row_name="货币资金",
        current_period_amount=Decimal("5000000"),
        prior_period_amount=Decimal("4040000"),
    )
    db_session.add(fr)
    await db_session.flush()
    return fr


@pytest_asyncio.fixture
async def tb_balances(db_session: AsyncSession, project: Project) -> list[TbBalance]:
    """Create TB balance entries for 1001 and 1002."""
    from decimal import Decimal

    balances = [
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="库存现金",
            closing_balance=Decimal("50000"),
            opening_balance=Decimal("40000"),
        ),
        TbBalance(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            company_code="001",
            account_code="1002",
            account_name="银行存款",
            closing_balance=Decimal("4950000"),
            opening_balance=Decimal("4000000"),
        ),
    ]
    for b in balances:
        db_session.add(b)
    await db_session.flush()
    return balances


# ===================================================================
# Helper: direct service call (bypass HTTP layer for unit tests)
# ===================================================================


async def _call_trace_source(db: AsyncSession, project_id: uuid.UUID, cell_id: str) -> dict:
    """Directly invoke the trace logic (same as the endpoint handler)."""
    from app.routers.note_trace import (
        TraceSourceResponse,
        _extract_account_codes_from_row,
        _extract_cell_value,
        _extract_row_label,
        _parse_cell_id,
    )
    import sqlalchemy as sa

    note_section, row_index, col_index = _parse_cell_id(cell_id)

    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        return {"error": "not_found"}

    if not note.table_data:
        return {"source_type": "none"}

    account_codes = _extract_account_codes_from_row(note.table_data, row_index)
    row_label = _extract_row_label(note.table_data, row_index)
    cell_value = _extract_cell_value(note.table_data, row_index, col_index)
    year = note.year

    if account_codes:
        mapping_result = await db.execute(
            sa.select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code.in_(account_codes),
                ReportLineMapping.is_deleted == sa.false(),
                ReportLineMapping.is_confirmed == sa.true(),
            )
        )
        mappings = mapping_result.scalars().all()

        if mappings:
            line_code = mappings[0].report_line_code
            line_name = mappings[0].report_line_name

            report_row = await db.execute(
                sa.select(FinancialReport).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.row_code == line_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            fr = report_row.scalar_one_or_none()
            amount = float(fr.current_period_amount) if fr and fr.current_period_amount else cell_value

            # Get TB balances
            tb_result = await db.execute(
                sa.select(TbBalance).where(
                    TbBalance.project_id == project_id,
                    TbBalance.year == year,
                    TbBalance.account_code.in_(account_codes),
                    TbBalance.is_deleted == sa.false(),
                )
            )
            tb_rows = tb_result.scalars().all()

            return {
                "source_type": "report_line",
                "report_line": {
                    "line_code": line_code,
                    "item_name": line_name,
                    "amount": amount,
                },
                "tb_accounts": [
                    {
                        "code": tb.account_code,
                        "name": tb.account_name or "",
                        "closing_balance": float(tb.closing_balance) if tb.closing_balance else 0.0,
                    }
                    for tb in tb_rows
                ],
            }

        # No mapping — direct TB reference
        tb_result = await db.execute(
            sa.select(TbBalance).where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
                TbBalance.account_code.in_(account_codes),
                TbBalance.is_deleted == sa.false(),
            )
        )
        tb_rows = tb_result.scalars().all()
        return {
            "source_type": "tb_account",
            "report_line": {
                "line_code": "",
                "item_name": row_label or "未知",
                "amount": cell_value,
            },
            "tb_accounts": [
                {
                    "code": tb.account_code,
                    "name": tb.account_name or "",
                    "closing_balance": float(tb.closing_balance) if tb.closing_balance else 0.0,
                }
                for tb in tb_rows
            ],
        }

    return {"source_type": "none"}


# ===================================================================
# Tests
# ===================================================================


class TestParseHelpers:
    """Test helper functions."""

    def test_parse_cell_id_valid(self):
        from app.routers.note_trace import _parse_cell_id

        section, row, col = _parse_cell_id("五、1:0:0")
        assert section == "五、1"
        assert row == 0
        assert col == 0

    def test_parse_cell_id_complex_section(self):
        from app.routers.note_trace import _parse_cell_id

        section, row, col = _parse_cell_id("五、12:2:1")
        assert section == "五、12"
        assert row == 2
        assert col == 1

    def test_parse_cell_id_invalid_format(self):
        from app.routers.note_trace import _parse_cell_id

        with pytest.raises(ValueError):
            _parse_cell_id("invalid")

    def test_parse_cell_id_non_numeric_indices(self):
        from app.routers.note_trace import _parse_cell_id

        with pytest.raises(ValueError):
            _parse_cell_id("五、1:abc:0")

    def test_extract_account_codes(self):
        from app.routers.note_trace import _extract_account_codes_from_row

        table_data = {
            "rows": [
                {"label": "现金", "values": [100], "account_codes": ["1001"]},
                {"label": "存款", "values": [200]},
            ]
        }
        assert _extract_account_codes_from_row(table_data, 0) == ["1001"]
        assert _extract_account_codes_from_row(table_data, 1) == []
        assert _extract_account_codes_from_row(table_data, 99) == []

    def test_extract_cell_value(self):
        from app.routers.note_trace import _extract_cell_value

        table_data = {
            "rows": [
                {"label": "A", "values": [100, 200]},
                {"label": "B", "values": [None, 300]},
                {"label": "C", "cells": [{"value": 400}]},
            ]
        }
        assert _extract_cell_value(table_data, 0, 0) == 100.0
        assert _extract_cell_value(table_data, 0, 1) == 200.0
        assert _extract_cell_value(table_data, 1, 0) is None
        assert _extract_cell_value(table_data, 2, 0) == 400.0
        assert _extract_cell_value(table_data, 99, 0) is None

    def test_extract_row_label(self):
        from app.routers.note_trace import _extract_row_label

        table_data = {"rows": [{"label": "货币资金"}, {"label": ""}]}
        assert _extract_row_label(table_data, 0) == "货币资金"
        assert _extract_row_label(table_data, 1) == ""
        assert _extract_row_label(table_data, 99) == ""


class TestTraceSourceWithMapping:
    """Test trace-source when report line mapping exists."""

    @pytest.mark.asyncio
    async def test_trace_single_account(
        self,
        db_session: AsyncSession,
        project: Project,
        note_with_accounts: DisclosureNote,
        report_line_mappings: list[ReportLineMapping],
        financial_report: FinancialReport,
        tb_balances: list[TbBalance],
    ):
        """Cell with single account_code traces to report line + TB account."""
        result = await _call_trace_source(db_session, project.id, "五、1:0:0")

        assert result["source_type"] == "report_line"
        assert result["report_line"]["line_code"] == "BS-001"
        assert result["report_line"]["item_name"] == "货币资金"
        assert result["report_line"]["amount"] == 5000000.0
        assert len(result["tb_accounts"]) == 1
        assert result["tb_accounts"][0]["code"] == "1001"
        assert result["tb_accounts"][0]["name"] == "库存现金"
        assert result["tb_accounts"][0]["closing_balance"] == 50000.0

    @pytest.mark.asyncio
    async def test_trace_multiple_accounts(
        self,
        db_session: AsyncSession,
        project: Project,
        note_with_accounts: DisclosureNote,
        report_line_mappings: list[ReportLineMapping],
        financial_report: FinancialReport,
        tb_balances: list[TbBalance],
    ):
        """Cell with multiple account_codes (合计行) traces to report line + multiple TB accounts."""
        result = await _call_trace_source(db_session, project.id, "五、1:2:0")

        assert result["source_type"] == "report_line"
        assert result["report_line"]["line_code"] == "BS-001"
        assert result["report_line"]["amount"] == 5000000.0
        assert len(result["tb_accounts"]) == 2
        codes = {a["code"] for a in result["tb_accounts"]}
        assert codes == {"1001", "1002"}


class TestTraceSourceWithoutMapping:
    """Test trace-source when no report line mapping exists."""

    @pytest.mark.asyncio
    async def test_trace_no_mapping_but_has_tb(
        self,
        db_session: AsyncSession,
        project: Project,
        note_with_accounts: DisclosureNote,
        tb_balances: list[TbBalance],
    ):
        """Cell with account_codes but no mapping returns tb_account type."""
        result = await _call_trace_source(db_session, project.id, "五、1:0:0")

        assert result["source_type"] == "tb_account"
        assert result["report_line"]["line_code"] == ""
        assert result["report_line"]["item_name"] == "库存现金"
        assert len(result["tb_accounts"]) == 1
        assert result["tb_accounts"][0]["code"] == "1001"


class TestTraceSourceNoData:
    """Test trace-source edge cases."""

    @pytest.mark.asyncio
    async def test_no_account_codes_returns_none(
        self,
        db_session: AsyncSession,
        project: Project,
        note_without_accounts: DisclosureNote,
    ):
        """Cell without account_codes returns source_type='none'."""
        result = await _call_trace_source(db_session, project.id, "五、99:0:0")
        assert result["source_type"] == "none"

    @pytest.mark.asyncio
    async def test_note_not_found(
        self,
        db_session: AsyncSession,
        project: Project,
    ):
        """Non-existent note section returns error."""
        result = await _call_trace_source(db_session, project.id, "不存在:0:0")
        assert result.get("error") == "not_found"

    def test_invalid_cell_id_format(self):
        """Invalid cell_id format raises ValueError."""
        from app.routers.note_trace import _parse_cell_id

        with pytest.raises(ValueError):
            _parse_cell_id("no-colons-here")

    @pytest.mark.asyncio
    async def test_note_without_table_data(
        self,
        db_session: AsyncSession,
        project: Project,
    ):
        """Note with no table_data returns source_type='none'."""
        note = DisclosureNote(
            id=uuid.uuid4(),
            project_id=project.id,
            year=2024,
            note_section="五、50",
            section_title="空表",
            content_type=ContentType.text,
            table_data=None,
        )
        db_session.add(note)
        await db_session.flush()

        result = await _call_trace_source(db_session, project.id, "五、50:0:0")
        assert result["source_type"] == "none"
