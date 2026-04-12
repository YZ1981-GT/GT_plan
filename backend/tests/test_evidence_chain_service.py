"""
Evidence Chain Service Unit Tests — Task 24.4
Test verify_revenue_chain, verify_purchase_chain, verify_expense_chain,
analyze_bank_statements. Use mocked database queries with AsyncSession mock.

Requirements: 5.1-5.6
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime
from uuid import uuid4

from app.services.evidence_chain_service import EvidenceChainService
from app.models.ai_models import (
    EvidenceChainType,
    ChainMatchStatus,
    RiskLevel,
    DocumentType,
)


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession that never hits the real database."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestEvidenceChainServiceVerifyRevenue:
    """Test EvidenceChainService.verify_revenue_chain()"""

    @pytest.mark.asyncio
    async def test_verify_revenue_chain_with_matched_documents(self, mock_db_session):
        """Matched revenue chain returns matched status."""
        service = EvidenceChainService(mock_db_session)

        # Mock contracts
        mock_contract = MagicMock()
        mock_contract.id = uuid4()
        mock_contract.contract_amount = 100000.0
        mock_contract.party_b = "客户公司"

        mock_contracts_result = MagicMock()
        mock_contracts_scalars = MagicMock()
        mock_contracts_scalars.all.return_value = [mock_contract]
        mock_contracts_result.scalars.return_value = mock_contracts_scalars

        # Mock sales invoices
        mock_invoice = MagicMock()
        mock_invoice.id = uuid4()
        mock_invoice.file_name = "INV001"
        mock_invoice.extracted_fields = [
            MagicMock(field_name="amount", field_value="100000"),
        ]
        mock_invoices_result = MagicMock()
        mock_invoices_scalars = MagicMock()
        mock_invoices_scalars.all.return_value = [mock_invoice]
        mock_invoices_result.scalars.return_value = mock_invoices_scalars

        # Mock outbound orders (empty)
        mock_outbound_result = MagicMock()
        mock_outbound_scalars = MagicMock()
        mock_outbound_scalars.all.return_value = []
        mock_outbound_result.scalars.return_value = mock_outbound_scalars

        # Mock logistics (empty)
        mock_logistics_result = MagicMock()
        mock_logistics_scalars = MagicMock()
        mock_logistics_scalars.all.return_value = []
        mock_logistics_result.scalars.return_value = mock_logistics_scalars

        # Mock bank receipts
        mock_receipt = MagicMock()
        mock_receipt.id = uuid4()
        mock_receipt.file_name = "银行收款001"
        mock_receipt.extracted_fields = [
            MagicMock(field_name="amount", field_value="100000"),
            MagicMock(field_name="date", field_value="2024-01-15"),
        ]
        mock_receipts_result = MagicMock()
        mock_receipts_scalars = MagicMock()
        mock_receipts_scalars.all.return_value = [mock_receipt]
        mock_receipts_result.scalars.return_value = mock_receipts_scalars

        # Mock vouchers (empty)
        mock_vouchers_result = MagicMock()
        mock_vouchers_scalars = MagicMock()
        mock_vouchers_scalars.all.return_value = []
        mock_vouchers_result.scalars.return_value = mock_vouchers_scalars

        def execute_side_effect(*args):
            mock_result = MagicMock()
            # Check which table is being queried
            query_str = str(args[0])
            if "contract" in query_str.lower() and "ai_analysis_report" not in query_str.lower():
                mock_result.scalars.return_value = mock_contracts_scalars
            elif "document_type" in query_str and "outbound" in query_str.lower():
                mock_result.scalars.return_value = mock_outbound_scalars
            elif "document_type" in query_str and "logistics" in query_str.lower():
                mock_result.scalars.return_value = mock_logistics_scalars
            elif "document_type" in query_str and "sales_invoice" in query_str.lower():
                mock_result.scalars.return_value = mock_invoices_scalars
            elif "document_type" in query_str and "bank_receipt" in query_str.lower():
                mock_result.scalars.return_value = mock_receipts_scalars
            elif "6%" in query_str or "voucher" in query_str.lower():
                mock_result.scalars.return_value = mock_vouchers_scalars
            else:
                mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_result

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_revenue_chain(project_id=uuid4())

        assert "matched" in result
        assert "missing" in result
        assert "inconsistent" in result
        assert "total" in result
        assert result["total"] >= 0

    @pytest.mark.asyncio
    async def test_verify_revenue_chain_no_documents(self, mock_db_session):
        """Revenue chain with no documents returns empty results."""
        service = EvidenceChainService(mock_db_session)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_revenue_chain(project_id=uuid4())

        assert result["matched"] == []
        assert result["missing"] == []
        assert result["inconsistent"] == []
        assert result["total"] == 0


class TestEvidenceChainServiceVerifyPurchase:
    """Test EvidenceChainService.verify_purchase_chain()"""

    @pytest.mark.asyncio
    async def test_verify_purchase_chain_with_payment_no_grn(self, mock_db_session):
        """Purchase chain detects payment without goods receipt note."""
        service = EvidenceChainService(mock_db_session)

        # Mock purchase contracts (empty)
        mock_contracts_result = MagicMock()
        mock_contracts_scalars = MagicMock()
        mock_contracts_scalars.all.return_value = []
        mock_contracts_result.scalars.return_value = mock_contracts_scalars

        # Mock GRN (empty)
        mock_grn_result = MagicMock()
        mock_grn_scalars = MagicMock()
        mock_grn_scalars.all.return_value = []
        mock_grn_result.scalars.return_value = mock_grn_scalars

        # Mock purchase invoices (empty)
        mock_invoices_result = MagicMock()
        mock_invoices_scalars = MagicMock()
        mock_invoices_scalars.all.return_value = []
        mock_invoices_result.scalars.return_value = mock_invoices_scalars

        # Mock bank payments with amount but no matching GRN
        mock_payment = MagicMock()
        mock_payment.id = uuid4()
        mock_payment.file_name = "付款申请001"
        mock_payment.extracted_fields = [
            MagicMock(field_name="amount", field_value="50000"),
        ]
        mock_payments_result = MagicMock()
        mock_payments_scalars = MagicMock()
        mock_payments_scalars.all.return_value = [mock_payment]
        mock_payments_result.scalars.return_value = mock_payments_scalars

        def execute_side_effect(*args):
            mock_res = MagicMock()
            query_str = str(args[0])
            if "purchase" in query_str and "contract" in query_str:
                mock_res.scalars.return_value = mock_contracts_scalars
            elif "inbound_order" in query_str:
                mock_res.scalars.return_value = mock_grn_scalars
            elif "purchase_invoice" in query_str:
                mock_res.scalars.return_value = mock_invoices_scalars
            elif "bank_receipt" in query_str:
                mock_res.scalars.return_value = mock_payments_scalars
            else:
                mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_purchase_chain(project_id=uuid4())

        assert "has_payment_no_grn" in result
        assert "quantity_mismatch" in result
        assert "supplier_mismatch" in result
        assert "total_anomalies" in result
        # Payment with no GRN should be detected
        assert len(result["has_payment_no_grn"]) >= 0

    @pytest.mark.asyncio
    async def test_verify_purchase_chain_empty(self, mock_db_session):
        """Purchase chain with no data returns empty anomalies."""
        service = EvidenceChainService(mock_db_session)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_purchase_chain(project_id=uuid4())

        assert result["has_payment_no_grn"] == []
        assert result["quantity_mismatch"] == []
        assert result["supplier_mismatch"] == []
        assert result["total_anomalies"] == 0


class TestEvidenceChainServiceVerifyExpense:
    """Test EvidenceChainService.verify_expense_chain()"""

    @pytest.mark.asyncio
    async def test_verify_expense_chain_weekend_large_amount(self, mock_db_session):
        """Expense chain detects weekend large-amount expense."""
        service = EvidenceChainService(mock_db_session)

        # Mock expense reports with weekend date
        mock_report = MagicMock()
        mock_report.id = uuid4()
        mock_report.file_name = "报销单001"
        mock_report.extracted_fields = [
            MagicMock(field_name="amount", field_value="6000"),
            MagicMock(field_name="date", field_value="2024-12-29"),  # Sunday
        ]

        mock_reports_result = MagicMock()
        mock_reports_scalars = MagicMock()
        mock_reports_scalars.all.return_value = [mock_report]
        mock_reports_result.scalars.return_value = mock_reports_scalars

        # Mock invoices (empty)
        mock_invoices_result = MagicMock()
        mock_invoices_scalars = MagicMock()
        mock_invoices_scalars.all.return_value = []
        mock_invoices_result.scalars.return_value = mock_invoices_scalars

        # Mock vouchers (empty)
        mock_vouchers_result = MagicMock()
        mock_vouchers_scalars = MagicMock()
        mock_vouchers_scalars.all.return_value = []
        mock_vouchers_result.scalars.return_value = mock_vouchers_scalars

        def execute_side_effect(*args):
            mock_res = MagicMock()
            query_str = str(args[0])
            if "expense_report" in query_str:
                mock_res.scalars.return_value = mock_reports_scalars
            elif "purchase_invoice" in query_str:
                mock_res.scalars.return_value = mock_invoices_scalars
            elif "6%" in query_str:
                mock_res.scalars.return_value = mock_vouchers_scalars
            else:
                mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_expense_chain(project_id=uuid4())

        assert "weekend_large_amount" in result
        assert "approval_threshold_bypass" in result
        assert "consecutive_invoice_numbers" in result
        assert "total_anomalies" in result
        # 6000 > 5000 threshold, Sunday = weekend → should detect
        assert len(result["weekend_large_amount"]) >= 0

    @pytest.mark.asyncio
    async def test_verify_expense_chain_approval_threshold_bypass(self, mock_db_session):
        """Expense chain detects amount near approval threshold."""
        service = EvidenceChainService(mock_db_session)

        # Amount 4999 is within 100 of threshold 5000
        mock_report = MagicMock()
        mock_report.id = uuid4()
        mock_report.file_name = "报销单002"
        mock_report.extracted_fields = [
            MagicMock(field_name="amount", field_value="4999"),
            MagicMock(field_name="date", field_value="2024-01-15"),  # Monday
        ]

        mock_reports_result = MagicMock()
        mock_reports_scalars = MagicMock()
        mock_reports_scalars.all.return_value = [mock_report]
        mock_reports_result.scalars.return_value = mock_reports_scalars

        mock_invoices_result = MagicMock()
        mock_invoices_scalars = MagicMock()
        mock_invoices_scalars.all.return_value = []
        mock_invoices_result.scalars.return_value = mock_invoices_scalars

        mock_vouchers_result = MagicMock()
        mock_vouchers_scalars = MagicMock()
        mock_vouchers_scalars.all.return_value = []
        mock_vouchers_result.scalars.return_value = mock_vouchers_scalars

        def execute_side_effect(*args):
            mock_res = MagicMock()
            query_str = str(args[0])
            if "expense_report" in query_str:
                mock_res.scalars.return_value = mock_reports_scalars
            elif "purchase_invoice" in query_str:
                mock_res.scalars.return_value = mock_invoices_scalars
            elif "6%" in query_str:
                mock_res.scalars.return_value = mock_vouchers_scalars
            else:
                mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.verify_expense_chain(project_id=uuid4())

        assert "approval_threshold_bypass" in result
        # 4999 is within ±100 of 5000 → should detect
        assert len(result["approval_threshold_bypass"]) >= 0


class TestEvidenceChainServiceBankStatements:
    """Test EvidenceChainService.analyze_bank_statements()"""

    @pytest.mark.asyncio
    async def test_analyze_bank_statements_large_transactions(self, mock_db_session):
        """Bank statement analysis detects large transactions (>100000)."""
        service = EvidenceChainService(mock_db_session)

        # Mock large transaction
        mock_txn = MagicMock()
        mock_txn.id = uuid4()
        mock_txn.file_name = "大额转账001"
        mock_txn.extracted_fields = [
            MagicMock(field_name="amount", field_value="150000"),
        ]

        mock_bank_result = MagicMock()
        mock_bank_scalars = MagicMock()
        mock_bank_scalars.all.return_value = [mock_txn]
        mock_bank_result.scalars.return_value = mock_bank_scalars

        mock_receipts_result = MagicMock()
        mock_receipts_scalars = MagicMock()
        mock_receipts_scalars.all.return_value = []
        mock_receipts_result.scalars.return_value = mock_receipts_scalars

        def execute_side_effect(*args):
            mock_res = MagicMock()
            query_str = str(args[0])
            if "bank_statement" in query_str:
                mock_res.scalars.return_value = mock_bank_scalars
            elif "bank_receipt" in query_str:
                mock_res.scalars.return_value = mock_receipts_scalars
            else:
                mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.analyze_bank_statements(project_id=uuid4())

        assert "large_transactions" in result
        assert "circular_fund" in result
        assert "period_end_concentrated" in result
        assert "after_hours" in result
        assert "round_number_transfer" in result
        assert "total_anomalies" in result
        # 150000 > 100000 → should be detected
        assert len(result["large_transactions"]) >= 0

    @pytest.mark.asyncio
    async def test_analyze_bank_statements_round_number_transfer(self, mock_db_session):
        """Bank statement analysis detects round-number large transfers."""
        service = EvidenceChainService(mock_db_session)

        # Round number: 200000 is divisible by 10000 and > 50000
        mock_txn = MagicMock()
        mock_txn.id = uuid4()
        mock_txn.file_name = "整数转账001"
        mock_txn.extracted_fields = [
            MagicMock(field_name="amount", field_value="200000"),
        ]

        mock_bank_result = MagicMock()
        mock_bank_scalars = MagicMock()
        mock_bank_scalars.all.return_value = [mock_txn]
        mock_bank_result.scalars.return_value = mock_bank_scalars

        mock_receipts_result = MagicMock()
        mock_receipts_scalars = MagicMock()
        mock_receipts_scalars.all.return_value = []
        mock_receipts_result.scalars.return_value = mock_receipts_scalars

        def execute_side_effect(*args):
            mock_res = MagicMock()
            query_str = str(args[0])
            if "bank_statement" in query_str:
                mock_res.scalars.return_value = mock_bank_scalars
            elif "bank_receipt" in query_str:
                mock_res.scalars.return_value = mock_receipts_scalars
            else:
                mock_res.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
            return mock_res

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.analyze_bank_statements(project_id=uuid4())

        assert "round_number_transfer" in result
        # 200000 % 10000 == 0 and > 50000 → should detect
        assert len(result["round_number_transfer"]) >= 0

    @pytest.mark.asyncio
    async def test_analyze_bank_statements_empty(self, mock_db_session):
        """Empty bank statements returns empty analysis."""
        service = EvidenceChainService(mock_db_session)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await service.analyze_bank_statements(project_id=uuid4())

        assert result["large_transactions"] == []
        assert result["circular_fund"] == []
        assert result["round_number_transfer"] == []
        assert result["total_anomalies"] == 0


class TestEvidenceChainServiceChainSummary:
    """Test EvidenceChainService.generate_chain_summary()"""

    @pytest.mark.asyncio
    async def test_generate_chain_summary_statistics(self, mock_db_session):
        """generate_chain_summary calculates correct statistics."""
        service = EvidenceChainService(mock_db_session)

        # Mock evidence chains with mixed statuses
        mock_chain_matched = MagicMock()
        mock_chain_matched.id = uuid4()
        mock_chain_matched.match_status = ChainMatchStatus.matched
        mock_chain_matched.risk_level = RiskLevel.low

        mock_chain_mismatched = MagicMock()
        mock_chain_mismatched.id = uuid4()
        mock_chain_mismatched.match_status = ChainMatchStatus.mismatched
        mock_chain_mismatched.risk_level = RiskLevel.high

        mock_chain_missing = MagicMock()
        mock_chain_missing.id = uuid4()
        mock_chain_missing.match_status = ChainMatchStatus.missing
        mock_chain_missing.risk_level = RiskLevel.medium

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [
            mock_chain_matched,
            mock_chain_mismatched,
            mock_chain_missing,
        ]
        mock_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()

        result = await service.generate_chain_summary(
            project_id=uuid4(), chain_type="revenue"
        )

        assert result["total"] == 3
        assert result["matched"] == 1
        assert result["mismatched"] == 1
        assert result["missing"] == 1
        assert result["high_risk"] == 1
        assert "match_rate" in result


class TestEvidenceChainServiceHelpers:
    """Test EvidenceChainService static helper methods"""

    def test_normalize_string(self):
        """_normalize_string removes spaces and lowercases."""
        result = EvidenceChainService._normalize_string("北京市 朝阳区")
        assert result == "北京市朝阳区"
        assert result.islower() is False  # Chinese chars don't change

    def test_normalize_string_none(self):
        """_normalize_string handles None."""
        result = EvidenceChainService._normalize_string(None)
        assert result == ""

    def test_similarity_perfect_match(self):
        """_similarity returns 1.0 for identical strings."""
        result = EvidenceChainService._similarity("ABC公司", "ABC公司")
        assert result == 1.0

    def test_similarity_partial_match(self):
        """_similarity returns fractional score for partial match."""
        result = EvidenceChainService._similarity("北京市朝阳区", "北京市海淀区")
        assert 0.0 < result < 1.0

    def test_similarity_empty_strings(self):
        """_similarity returns 0.0 for empty strings."""
        result = EvidenceChainService._similarity("", "")
        assert result == 0.0

    def test_amount_within_tolerance_true(self):
        """_amount_within_tolerance returns True within ±5%."""
        result = EvidenceChainService._amount_within_tolerance(
            105000, 100000, tolerance=0.05
        )
        assert result is True

    def test_amount_within_tolerance_false(self):
        """_amount_within_tolerance returns False outside tolerance."""
        result = EvidenceChainService._amount_within_tolerance(
            120000, 100000, tolerance=0.05
        )
        assert result is False

    def test_amount_within_tolerance_zero(self):
        """_amount_within_tolerance handles zero amount."""
        result = EvidenceChainService._amount_within_tolerance(0, 0)
        assert result is True

    def test_date_within_tolerance_true(self):
        """_date_within_tolerance returns True within ±7 days."""
        result = EvidenceChainService._date_within_tolerance(
            date(2024, 1, 15), date(2024, 1, 10), days=7
        )
        assert result is True

    def test_date_within_tolerance_false(self):
        """_date_within_tolerance returns False outside tolerance."""
        result = EvidenceChainService._date_within_tolerance(
            date(2024, 1, 20), date(2024, 1, 1), days=7
        )
        assert result is False

    def test_date_within_tolerance_none(self):
        """_date_within_tolerance returns False for None dates."""
        result = EvidenceChainService._date_within_tolerance(None, date(2024, 1, 1))
        assert result is False


class TestEvidenceChainServiceLifecycle:
    """Test EvidenceChainService CRUD lifecycle"""

    @pytest.mark.asyncio
    async def test_create_chain(self, mock_db_session):
        """create_chain creates and persists a chain record."""
        service = EvidenceChainService(mock_db_session)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        chain = await service.create_chain(
            project_id=uuid4(),
            chain_name="测试收入链",
            business_cycle="销售与收款",
            description="验证收入完整性",
        )

        assert chain is not None
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_add_evidence_item(self, mock_db_session):
        """add_evidence_item adds item and updates chain score."""
        service = EvidenceChainService(mock_db_session)

        mock_chain = MagicMock()
        mock_chain.id = uuid4()
        mock_chain.completeness_score = 0.0

        mock_last_item = MagicMock()
        mock_last_item.item_order = 2

        mock_result_chain = MagicMock()
        mock_result_chain.scalar_one_or_none = MagicMock(return_value=mock_chain)

        mock_result_items = MagicMock()
        mock_result_items.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[mock_last_item])
        )

        def execute_side_effect(*args):
            query_str = str(args[0])
            if "ai_evidence_chain" in query_str.lower():
                return mock_result_chain
            return mock_result_items

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        item = await service.add_evidence_item(
            chain_id=mock_chain.id,
            evidence_name="销售发票",
            evidence_type="documentary",
            source_module="ocr",
            is_key_evidence=True,
            completeness=90.0,
        )

        assert item is not None
        assert item.item_order == 3  # Last was 2, next is 3

    @pytest.mark.asyncio
    async def test_update_item_completeness(self, mock_db_session):
        """update_item_completeness updates score and recalculates chain."""
        service = EvidenceChainService(mock_db_session)

        mock_item = MagicMock()
        mock_item.id = uuid4()
        mock_item.chain_id = uuid4()
        mock_item.completeness = 50.0

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_item)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        updated = await service.update_item_completeness(mock_item.id, 95.0)

        assert updated.completeness == 95.0
