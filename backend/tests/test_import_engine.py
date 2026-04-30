"""数据导入引擎单元测试

Validates: Requirements 4.1, 4.2, 4.7-4.20, 4.23
"""

import io
import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project
from app.models.audit_platform_models import (
    AccountChart,
    AccountSource,
    AccountDirection,
    AccountCategory,
    ImportBatch,
    ImportStatus,
    TbBalance,
    TbLedger,
    TbAuxBalance,
    TbAuxLedger,
)
from app.models.audit_platform_schemas import BasicInfoSchema

# SQLite JSONB compat
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

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


@pytest_asyncio.fixture(autouse=True)
async def patch_import_queue_async_session(monkeypatch):
    from app.services import import_queue_service

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(import_queue_service, "async_session", session_factory)
    yield


async def _create_test_project(db: AsyncSession) -> Project:
    """Create a test project."""
    from app.services import project_wizard_service as svc

    data = BasicInfoSchema(
        client_name="测试客户",
        audit_year=2024,
        project_type="annual",
        accounting_standard="enterprise",
    )
    return await svc.create_project(data, db)


def _make_csv_upload(content: str, filename: str = "data.csv") -> UploadFile:
    """Create a mock UploadFile from CSV string."""
    file_bytes = content.encode("utf-8-sig")
    return UploadFile(filename=filename, file=io.BytesIO(file_bytes))


def _make_xlsx_bytes(rows: list[list[object]], sheet_name: str = "Sheet1") -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


# ===================================================================
# GenericParser Tests
# ===================================================================


class TestGenericParser:
    """Validates: Requirements 4.1, 4.2"""

    def test_parse_balance_csv(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
            "1002,银行存款,50000.00,10000.00,8000.00,52000.00\n"
        )
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8-sig"), "tb_balance")

        assert len(result) == 2
        assert result[0]["account_code"] == "1001"
        assert result[0]["account_name"] == "库存现金"
        assert result[0]["opening_balance"] == Decimal("1000.00")
        assert result[0]["debit_amount"] == Decimal("500.00")
        assert result[0]["credit_amount"] == Decimal("300.00")
        assert result[0]["closing_balance"] == Decimal("1200.00")

    def test_parse_ledger_csv(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = (
            "科目编码,科目名称,凭证日期,凭证号,借方金额,贷方金额,摘要\n"
            "1001,库存现金,2024-01-15,PZ-001,500.00,0,收到现金\n"
            "1002,银行存款,2024-01-15,PZ-001,0,500.00,转账\n"
        )
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8-sig"), "tb_ledger")

        assert len(result) == 2
        assert result[0]["voucher_date"] == date(2024, 1, 15)
        assert result[0]["voucher_no"] == "PZ-001"
        assert result[0]["debit_amount"] == Decimal("500.00")
        assert result[0]["summary"] == "收到现金"

    def test_parse_aux_balance_csv(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = (
            "科目编码,辅助类型,辅助编码,辅助名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1122,customer,C001,客户A,10000.00,5000.00,3000.00,12000.00\n"
        )
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8-sig"), "tb_aux_balance")

        assert len(result) == 1
        assert result[0]["aux_type"] == "customer"
        assert result[0]["aux_code"] == "C001"
        assert result[0]["closing_balance"] == Decimal("12000.00")

    def test_parse_aux_ledger_csv(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = (
            "科目编码,辅助类型,辅助编码,辅助名称,凭证日期,凭证号,借方金额,贷方金额,摘要\n"
            "1122,customer,C001,客户A,2024-03-01,PZ-010,5000.00,0,销售收款\n"
        )
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8-sig"), "tb_aux_ledger")

        assert len(result) == 1
        assert result[0]["aux_type"] == "customer"
        assert result[0]["voucher_date"] == date(2024, 3, 1)

    def test_parse_empty_csv(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = "科目编码,科目名称,期初余额\n"
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8-sig"), "tb_balance")
        assert result == []

    def test_parse_english_columns(self):
        from app.services.import_engine.parsers import GenericParser

        csv_content = (
            "account_code,account_name,opening_balance,debit_amount,credit_amount,closing_balance\n"
            "1001,Cash,1000,500,300,1200\n"
        )
        parser = GenericParser()
        result = parser.parse(csv_content.encode("utf-8"), "tb_balance")

        assert len(result) == 1
        assert result[0]["account_code"] == "1001"
        assert result[0]["opening_balance"] == Decimal("1000")


# ===================================================================
# ParserFactory Tests
# ===================================================================


class TestParserFactory:
    """Validates: Requirements 4.1"""

    def test_get_generic_parser(self):
        from app.services.import_engine.parsers import ParserFactory, GenericParser

        parser = ParserFactory.get_parser("generic")
        assert isinstance(parser, GenericParser)

    def test_get_yonyou_parser(self):
        from app.services.import_engine.parsers import ParserFactory, YonyouParser

        parser = ParserFactory.get_parser("yonyou")
        assert isinstance(parser, YonyouParser)

    def test_get_kingdee_parser(self):
        from app.services.import_engine.parsers import ParserFactory, KingdeeParser

        parser = ParserFactory.get_parser("kingdee")
        assert isinstance(parser, KingdeeParser)

    def test_get_sap_parser(self):
        from app.services.import_engine.parsers import ParserFactory, SAPParser

        parser = ParserFactory.get_parser("sap")
        assert isinstance(parser, SAPParser)

    def test_get_unknown_parser_raises(self):
        from app.services.import_engine.parsers import ParserFactory

        with pytest.raises(Exception) as exc_info:
            ParserFactory.get_parser("unknown")
        assert exc_info.value.status_code == 400


# ===================================================================
# Validation Rules Tests
# ===================================================================


class TestYearConsistencyRule:
    """Validates: Requirements 4.13, 4.14"""

    def test_matching_year_passes(self):
        from app.services.import_engine.validation import (
            YearConsistencyRule,
            ValidationContext,
        )

        rule = YearConsistencyRule()
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001"},
            {"voucher_date": date(2024, 6, 30), "voucher_no": "PZ-002"},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_mismatched_year_fails(self):
        from app.services.import_engine.validation import (
            YearConsistencyRule,
            ValidationContext,
        )

        rule = YearConsistencyRule()
        data = [
            {"voucher_date": date(2023, 12, 31), "voucher_no": "PZ-001"},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-002"},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is False
        assert result.severity == "reject"

    def test_applies_to_ledger(self):
        from app.services.import_engine.validation import YearConsistencyRule

        rule = YearConsistencyRule()
        assert rule.applies_to("tb_ledger") is True
        assert rule.applies_to("tb_balance") is False


class TestDebitCreditBalanceRule:
    """Validates: Requirements 4.7, 4.8"""

    def test_balanced_voucher_passes(self):
        from app.services.import_engine.validation import (
            DebitCreditBalanceRule,
            ValidationContext,
        )

        rule = DebitCreditBalanceRule()
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "debit_amount": Decimal("0"), "credit_amount": Decimal("500")},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_unbalanced_voucher_fails(self):
        from app.services.import_engine.validation import (
            DebitCreditBalanceRule,
            ValidationContext,
        )

        rule = DebitCreditBalanceRule()
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "debit_amount": Decimal("0"), "credit_amount": Decimal("300")},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is False
        assert result.severity == "reject"
        assert len(result.details) == 1

    def test_applies_to_ledger(self):
        from app.services.import_engine.validation import DebitCreditBalanceRule

        rule = DebitCreditBalanceRule()
        assert rule.applies_to("tb_ledger") is True
        assert rule.applies_to("tb_balance") is False


class TestOpeningClosingRule:
    """Validates: Requirements 4.9, 4.10"""

    def test_correct_debit_account_passes(self):
        from app.services.import_engine.validation import (
            OpeningClosingRule,
            ValidationContext,
        )

        rule = OpeningClosingRule()
        # Debit account: opening + debit - credit = closing
        data = [
            {
                "account_code": "1001",
                "opening_balance": Decimal("1000"),
                "debit_amount": Decimal("500"),
                "credit_amount": Decimal("300"),
                "closing_balance": Decimal("1200"),
            }
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_correct_credit_account_passes(self):
        from app.services.import_engine.validation import (
            OpeningClosingRule,
            ValidationContext,
        )

        rule = OpeningClosingRule()
        # Credit account: opening - debit + credit = closing
        data = [
            {
                "account_code": "2001",
                "opening_balance": Decimal("5000"),
                "debit_amount": Decimal("1000"),
                "credit_amount": Decimal("2000"),
                "closing_balance": Decimal("6000"),
            }
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_incorrect_balance_fails(self):
        from app.services.import_engine.validation import (
            OpeningClosingRule,
            ValidationContext,
        )

        rule = OpeningClosingRule()
        data = [
            {
                "account_code": "1001",
                "opening_balance": Decimal("1000"),
                "debit_amount": Decimal("500"),
                "credit_amount": Decimal("300"),
                "closing_balance": Decimal("9999"),  # Wrong
            }
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is False
        assert result.severity == "warning"


class TestDuplicateDetectionRule:
    """Validates: Requirements 4.15"""

    def test_no_duplicates_passes(self):
        from app.services.import_engine.validation import (
            DuplicateDetectionRule,
            ValidationContext,
        )

        rule = DuplicateDetectionRule()
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001"},
            {"voucher_date": date(2024, 1, 16), "voucher_no": "PZ-002"},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_duplicates_detected(self):
        from app.services.import_engine.validation import (
            DuplicateDetectionRule,
            ValidationContext,
        )

        rule = DuplicateDetectionRule()
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001"},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001"},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001"},
        ]
        ctx = ValidationContext(project_year=2024)
        result = rule.execute(data, ctx)
        assert result.passed is False
        assert result.severity == "warning"


class TestAccountCompletenessRule:
    """Validates: Requirements 4.11, 4.12"""

    def test_all_accounts_exist_passes(self):
        from app.services.import_engine.validation import (
            AccountCompletenessRule,
            ValidationContext,
        )

        rule = AccountCompletenessRule()
        data = [
            {"account_code": "1001"},
            {"account_code": "1002"},
        ]
        ctx = ValidationContext(
            project_year=2024,
            account_codes={"1001", "1002", "2001"},
        )
        result = rule.execute(data, ctx)
        assert result.passed is True

    def test_missing_accounts_detected(self):
        from app.services.import_engine.validation import (
            AccountCompletenessRule,
            ValidationContext,
        )

        rule = AccountCompletenessRule()
        data = [
            {"account_code": "1001"},
            {"account_code": "9999"},
        ]
        ctx = ValidationContext(
            project_year=2024,
            account_codes={"1001", "1002"},
        )
        result = rule.execute(data, ctx)
        assert result.passed is False
        assert result.severity == "warning"


# ===================================================================
# Cross-table Validation Tests
# ===================================================================


class TestLedgerBalanceReconcileRule:
    """Validates: Requirements 4.17, 4.18"""

    def test_matching_totals_passes(self):
        from app.services.import_engine.validation import (
            LedgerBalanceReconcileRule,
            ValidationContext,
        )

        rule = LedgerBalanceReconcileRule()
        ledger_data = [
            {"account_code": "1001", "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
            {"account_code": "1001", "debit_amount": Decimal("300"), "credit_amount": Decimal("0")},
        ]
        balance_data = [
            {"account_code": "1001", "debit_amount": Decimal("800"), "credit_amount": Decimal("0")},
        ]
        ctx = ValidationContext(project_year=2024, balance_data=balance_data)
        result = rule.execute(ledger_data, ctx)
        assert result.passed is True

    def test_mismatched_totals_fails(self):
        from app.services.import_engine.validation import (
            LedgerBalanceReconcileRule,
            ValidationContext,
        )

        rule = LedgerBalanceReconcileRule()
        ledger_data = [
            {"account_code": "1001", "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
        ]
        balance_data = [
            {"account_code": "1001", "debit_amount": Decimal("999"), "credit_amount": Decimal("0")},
        ]
        ctx = ValidationContext(project_year=2024, balance_data=balance_data)
        result = rule.execute(ledger_data, ctx)
        assert result.passed is False


class TestAuxMainReconcileRule:
    """Validates: Requirements 4.19, 4.20"""

    def test_matching_totals_passes(self):
        from app.services.import_engine.validation import (
            AuxMainReconcileRule,
            ValidationContext,
        )

        rule = AuxMainReconcileRule()
        aux_data = [
            {"account_code": "1122", "closing_balance": Decimal("5000")},
            {"account_code": "1122", "closing_balance": Decimal("3000")},
        ]
        balance_data = [
            {"account_code": "1122", "closing_balance": Decimal("8000")},
        ]
        ctx = ValidationContext(project_year=2024, balance_data=balance_data)
        result = rule.execute(aux_data, ctx)
        assert result.passed is True

    def test_mismatched_totals_fails(self):
        from app.services.import_engine.validation import (
            AuxMainReconcileRule,
            ValidationContext,
        )

        rule = AuxMainReconcileRule()
        aux_data = [
            {"account_code": "1122", "closing_balance": Decimal("5000")},
        ]
        balance_data = [
            {"account_code": "1122", "closing_balance": Decimal("9999")},
        ]
        ctx = ValidationContext(project_year=2024, balance_data=balance_data)
        result = rule.execute(aux_data, ctx)
        assert result.passed is False


# ===================================================================
# ValidationEngine Tests
# ===================================================================


class TestValidationEngine:
    """Validates: Requirements 4.7-4.20"""

    def test_balance_validation_passes(self):
        from app.services.import_engine.validation import (
            ValidationEngine,
            ValidationContext,
        )

        engine = ValidationEngine()
        data = [
            {
                "account_code": "1001",
                "opening_balance": Decimal("1000"),
                "debit_amount": Decimal("500"),
                "credit_amount": Decimal("300"),
                "closing_balance": Decimal("1200"),
            }
        ]
        ctx = ValidationContext(project_year=2024, account_codes={"1001"})
        result = engine.validate(data, "tb_balance", ctx)
        assert result.passed is True

    def test_ledger_reject_stops_chain(self):
        from app.services.import_engine.validation import (
            ValidationEngine,
            ValidationContext,
        )

        engine = ValidationEngine()
        # Unbalanced voucher should cause reject
        data = [
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "account_code": "1001",
             "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
            {"voucher_date": date(2024, 1, 15), "voucher_no": "PZ-001",
             "account_code": "1002",
             "debit_amount": Decimal("0"), "credit_amount": Decimal("300")},
        ]
        ctx = ValidationContext(project_year=2024)
        result = engine.validate(data, "tb_ledger", ctx)
        assert result.passed is False
        assert result.has_reject is True


# ===================================================================
# ImportService Integration Tests
# ===================================================================


class TestImportService:
    """Validates: Requirements 4.3, 4.5, 4.23"""

    @pytest.mark.asyncio
    async def test_start_import_balance(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
            "1002,银行存款,50000.00,10000.00,8000.00,52000.00\n"
        )
        file = _make_csv_upload(csv_content)

        batch = await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )

        assert batch.status == ImportStatus.completed
        assert batch.record_count == 2
        assert batch.data_type == "tb_balance"

    @pytest.mark.asyncio
    async def test_smart_import_streaming_account_chart_csv(self, db_session: AsyncSession):
        from sqlalchemy import select
        from app.services.smart_import_engine import smart_import_streaming

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,借贷方向,父科目编码\n"
            "1001,库存现金,借,\n"
            "100101,人民币现金,借,1001\n"
        )

        result = await smart_import_streaming(
            project_id=project.id,
            file_contents=[("chart.csv", csv_content.encode("utf-8-sig"))],
            db=db_session,
            year_override=2024,
        )

        assert result["total_accounts"] == 2
        assert result["data_sheets_imported"]["tb_balance"] == 0
        assert result["data_sheets_imported"]["tb_ledger"] == 0

        query = await db_session.execute(
            select(AccountChart).where(
                AccountChart.project_id == project.id,
                AccountChart.source == AccountSource.client,
                AccountChart.is_deleted.is_(False),
            )
        )
        records = query.scalars().all()

        assert len(records) == 2
        assert {r.account_code for r in records} == {"1001", "100101"}

    @pytest.mark.asyncio
    async def test_smart_import_streaming_staged_dataset_failure_stops_import(
        self,
        db_session: AsyncSession,
        monkeypatch,
    ):
        from sqlalchemy import func, select
        from app.services.dataset_service import DatasetService
        from app.services.smart_import_engine import SmartImportError, smart_import_streaming

        project = await _create_test_project(db_session)
        project_id = project.id
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,100.00,20.00,10.00,110.00\n"
        )

        async def fail_create_staged(*args, **kwargs):
            raise RuntimeError("dataset store unavailable")

        monkeypatch.setattr(DatasetService, "create_staged", fail_create_staged)

        with pytest.raises(SmartImportError, match="创建数据集版本失败"):
            await smart_import_streaming(
                project_id=project.id,
                file_contents=[("balance.csv", csv_content.encode("utf-8-sig"))],
                db=db_session,
                year_override=2024,
            )

        await db_session.rollback()
        balance_count = await db_session.execute(
            select(func.count(TbBalance.id)).where(TbBalance.project_id == project_id)
        )
        assert balance_count.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_smart_import_streaming_activation_failure_keeps_previous_visible(
        self,
        db_session: AsyncSession,
        monkeypatch,
    ):
        from sqlalchemy import select
        from app.models.dataset_models import DatasetStatus
        from app.services.dataset_service import DatasetService
        from app.services.smart_import_engine import SmartImportError, smart_import_streaming

        project = await _create_test_project(db_session)
        project_id = project.id
        previous = await DatasetService.create_staged(db_session, project_id=project_id, year=2024)
        await DatasetService.activate(db_session, previous.id)
        db_session.add(TbBalance(
            project_id=project_id,
            year=2024,
            company_code="001",
            account_code="1001",
            account_name="旧库存现金",
            dataset_id=previous.id,
            is_deleted=False,
        ))
        await db_session.commit()

        async def fail_activate(*args, **kwargs):
            raise RuntimeError("activation failed")

        monkeypatch.setattr(DatasetService, "activate", fail_activate)
        csv_content = (
            "科目编码,科目名称,借贷方向,父科目编码\n"
            "1002,新银行存款,借,\n"
        )

        with pytest.raises(SmartImportError, match="数据集激活失败"):
            await smart_import_streaming(
                project_id=project_id,
                file_contents=[("chart.csv", csv_content.encode("utf-8-sig"))],
                db=db_session,
                year_override=2024,
            )

        old_row = (await db_session.execute(
            select(TbBalance).where(
                TbBalance.project_id == project_id,
                TbBalance.account_code == "1001",
            )
        )).scalar_one()
        await db_session.refresh(previous)

        assert old_row.is_deleted is False
        assert previous.status == DatasetStatus.active

    @pytest.mark.asyncio
    async def test_smart_import_streaming_blocks_large_full_mode_excel(
        self,
        db_session: AsyncSession,
        monkeypatch,
    ):
        from app.core.config import settings
        from app.services import smart_import_engine
        from app.services.smart_import_engine import SmartImportError, smart_import_streaming

        project = await _create_test_project(db_session)
        workbook_bytes = _make_xlsx_bytes(
            [
                ["科目编码", "科目名称"],
                ["1001", "库存现金"],
            ],
            sheet_name="科目表",
        )
        monkeypatch.setattr(settings, "LEDGER_IMPORT_FULL_MODE_MAX_FILE_MB", 1)
        monkeypatch.setattr(smart_import_engine, "_source_size_bytes", lambda _content: 2 * 1024 * 1024)

        with pytest.raises(SmartImportError, match="文件超过非只读 Excel 解析阈值"):
            await smart_import_streaming(
                project_id=project.id,
                file_contents=[("large-merged.xlsx", workbook_bytes)],
                db=db_session,
                year_override=2024,
            )

    @pytest.mark.asyncio
    async def test_smart_import_streaming_csv_ledger_missing_account_code_fails(self, db_session: AsyncSession):
        from sqlalchemy import func, select
        from app.services.smart_import_engine import smart_import_streaming

        project = await _create_test_project(db_session)
        csv_content = (
            "凭证日期,凭证号,借方金额,贷方金额,摘要\n"
            "2024-01-15,PZ-001,500.00,0,收到现金\n"
        )

        with pytest.raises(ValueError, match="CSV 序时账缺少必需列: 科目编码"):
            await smart_import_streaming(
                project_id=project.id,
                file_contents=[("ledger_missing_account_code.csv", csv_content.encode("utf-8-sig"))],
                db=db_session,
                year_override=2024,
            )

        ledger_count = await db_session.execute(
            select(func.count(TbLedger.id)).where(TbLedger.project_id == project.id)
        )
        assert ledger_count.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_smart_import_streaming_excel_account_chart_missing_name_fails(self, db_session: AsyncSession):
        from sqlalchemy import func, select
        from app.services.smart_import_engine import smart_import_streaming

        project = await _create_test_project(db_session)
        workbook_bytes = _make_xlsx_bytes(
            [
                ["科目编码"],
                ["1001"],
            ],
            sheet_name="科目表",
        )

        with pytest.raises(ValueError, match="科目表缺少必需列: 科目名称"):
            await smart_import_streaming(
                project_id=project.id,
                file_contents=[("chart_missing_name.xlsx", workbook_bytes)],
                db=db_session,
                year_override=2024,
            )

        chart_count = await db_session.execute(
            select(func.count(AccountChart.id)).where(
                AccountChart.project_id == project.id,
                AccountChart.source == AccountSource.client,
            )
        )
        assert chart_count.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_write_four_tables_legacy_path_is_disabled(self, db_session: AsyncSession):
        from app.services.smart_import_engine import write_four_tables

        project = await _create_test_project(db_session)

        with pytest.raises(RuntimeError, match="write_four_tables 已废弃"):
            await write_four_tables(
                project_id=project.id,
                year=2024,
                balance_rows=[],
                aux_balance_rows=[],
                ledger_rows=[],
                aux_ledger_rows=[],
                db=db_session,
            )

    @pytest.mark.asyncio
    async def test_start_import_ledger(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,凭证日期,凭证号,借方金额,贷方金额,摘要\n"
            "1001,库存现金,2024-01-15,PZ-001,500.00,0,收到现金\n"
            "1002,银行存款,2024-01-15,PZ-001,0,500.00,转账\n"
        )
        file = _make_csv_upload(csv_content)

        batch = await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_ledger",
            year=2024,
            db=db_session,
        )

        assert batch.status == ImportStatus.completed
        assert batch.record_count == 2

    @pytest.mark.asyncio
    async def test_start_import_unbalanced_ledger_fails(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,凭证日期,凭证号,借方金额,贷方金额\n"
            "1001,2024-01-15,PZ-001,500.00,0\n"
            "1002,2024-01-15,PZ-001,0,300.00\n"
        )
        file = _make_csv_upload(csv_content)

        batch = await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_ledger",
            year=2024,
            db=db_session,
        )

        # Should fail validation but return batch (not raise)
        assert batch.status == ImportStatus.failed
        assert batch.validation_summary is not None
        assert batch.validation_summary["has_reject"] is True

    @pytest.mark.asyncio
    async def test_rollback_import(self, db_session: AsyncSession):
        from app.services import import_service
        from sqlalchemy import select, func

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
        )
        file = _make_csv_upload(csv_content)

        batch = await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )
        assert batch.status == ImportStatus.completed

        # Verify records exist
        count_result = await db_session.execute(
            select(func.count(TbBalance.id)).where(
                TbBalance.import_batch_id == batch.id
            )
        )
        assert count_result.scalar_one() == 1

        # Rollback
        rolled_back = await import_service.rollback_import(batch.id, db_session)
        assert rolled_back.status == ImportStatus.rolled_back

        # Verify records deleted
        count_result = await db_session.execute(
            select(func.count(TbBalance.id)).where(
                TbBalance.import_batch_id == batch.id
            )
        )
        assert count_result.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_get_import_progress(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
        )
        file = _make_csv_upload(csv_content)

        batch = await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )

        progress = await import_service.get_import_progress(batch.id, db_session)
        assert progress.status == ImportStatus.completed
        assert progress.records_processed == 1
        assert progress.progress_percent == 100.0

    @pytest.mark.asyncio
    async def test_get_import_batches(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
        )
        file = _make_csv_upload(csv_content)

        await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )

        batches = await import_service.get_import_batches(project.id, db_session)
        assert len(batches) == 1
        assert batches[0].file_name == "data.csv"

    @pytest.mark.asyncio
    async def test_import_queue_lock_blocks_same_project(self, db_session: AsyncSession):
        from sqlalchemy import select
        from app.services.import_queue_service import ImportQueueService, IMPORT_JOB_DATA_TYPE

        project = await _create_test_project(db_session)

        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            "tester-a",
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        ok2, msg2, batch_id2 = await ImportQueueService.acquire_lock(
            project.id,
            "tester-b",
            db_session,
            source_type="smart_import",
            file_name="chart-2.xlsx",
            year=0,
        )
        assert ok2 is False
        assert batch_id2 is None
        assert "项目正在导入中" in msg2

        result = await db_session.execute(
            select(ImportBatch).where(ImportBatch.id == batch_id)
        )
        job_batch = result.scalar_one()
        assert job_batch.data_type == IMPORT_JOB_DATA_TYPE
        assert job_batch.status == ImportStatus.processing

    @pytest.mark.asyncio
    async def test_import_queue_status_falls_back_to_db_after_completion(self, db_session: AsyncSession):
        from app.services.import_queue_service import ImportQueueService

        project = await _create_test_project(db_session)

        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            "tester",
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        await ImportQueueService.complete_job(
            project.id,
            batch_id,
            db_session,
            message="导入完成",
            result={"total_imported": 2},
            year=2024,
            record_count=2,
        )

        status = await ImportQueueService.get_status(project.id, db_session)
        assert status is not None
        assert status["batch_id"] == str(batch_id)
        assert status["status"] == ImportStatus.completed.value
        assert status["progress"] == 100
        assert status["result"] == {"total_imported": 2}

    @pytest.mark.asyncio
    async def test_import_queue_processing_progress_persists_to_db(self, db_session: AsyncSession):
        from app.services.import_queue_service import ImportQueueService

        project = await _create_test_project(db_session)

        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            "tester",
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        ImportQueueService.update_progress(project.id, 35, "处理中")
        await asyncio.sleep(0.05)
        ImportQueueService.release_lock(project.id)

        status = await ImportQueueService.get_status(project.id, db_session)
        assert status is not None
        assert status["batch_id"] == str(batch_id)
        assert status["status"] == ImportStatus.processing.value
        assert status["progress"] == 35
        assert status["message"] == "处理中"

    @pytest.mark.asyncio
    async def test_get_import_batches_excludes_smart_job_batches(self, db_session: AsyncSession):
        from app.services import import_service
        from app.services.import_queue_service import ImportQueueService

        project = await _create_test_project(db_session)

        ok, msg, batch_id = await ImportQueueService.acquire_lock(
            project.id,
            "tester",
            db_session,
            source_type="smart_import",
            file_name="chart.xlsx",
            year=0,
        )
        assert ok is True
        assert batch_id is not None

        file = _make_csv_upload(
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
        )
        await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )

        batches = await import_service.get_import_batches(project.id, db_session)
        assert len(batches) == 1
        assert batches[0].data_type == "tb_balance"

    @pytest.mark.asyncio
    async def test_queue_unmapped(self, db_session: AsyncSession):
        from app.services import import_service

        project = await _create_test_project(db_session)
        csv_content = (
            "科目编码,科目名称,期初余额,借方发生额,贷方发生额,期末余额\n"
            "1001,库存现金,1000.00,500.00,300.00,1200.00\n"
            "9999,未知科目,100.00,0,0,100.00\n"
        )
        file = _make_csv_upload(csv_content)

        await import_service.start_import(
            project_id=project.id,
            file=file,
            source_type="generic",
            data_type="tb_balance",
            year=2024,
            db=db_session,
        )

        unmapped = await import_service.queue_unmapped(project.id, db_session)
        # All codes are unmapped since no mappings exist
        assert "1001" in unmapped
        assert "9999" in unmapped
