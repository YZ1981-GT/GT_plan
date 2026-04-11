"""数据导入引擎单元测试

Validates: Requirements 4.1, 4.2, 4.7-4.20, 4.23
"""

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import UploadFile
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
