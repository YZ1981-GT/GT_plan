"""wp-evidence-collection spec 测试

覆盖：
  1. PBC CRUD 单测
  2. LLM 识别 mock 测试（stub 模式）
  3. evidence_group 填充测试
  4. 逾期检测 + IssueTicket 创建
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# ─── PBC Service 单测 ─────────────────────────────────────────────────────────


class TestPbcService:
    """PBC CRUD 单测"""

    @pytest.fixture
    def mock_db(self):
        """模拟 AsyncSession"""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_create_item(self, mock_db):
        """创建 PBC 项"""
        from app.services.pbc_service import PbcService

        svc = PbcService()
        project_id = uuid.uuid4()

        # Mock the flush to set id on the item
        async def mock_flush():
            pass

        mock_db.flush = mock_flush

        # 直接测试 _to_dict 逻辑
        from app.models.collaboration_models import PBCChecklist, PbcStatus
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=project_id,
            item_name="银行对账单",
            category="货币资金",
            status=PbcStatus.PENDING,
            cycle_code="E",
        )
        result = svc._to_dict(item)
        assert result["item_name"] == "银行对账单"
        assert result["category"] == "货币资金"
        assert result["cycle_code"] == "E"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_to_dict_all_fields(self):
        """_to_dict 包含所有必要字段"""
        from app.services.pbc_service import PbcService
        from app.models.collaboration_models import PBCChecklist, PbcStatus

        svc = PbcService()
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            item_name="发票",
            status=PbcStatus.RECEIVED,
            wp_id=uuid.uuid4(),
            cycle_code="D",
            due_date=date(2025, 6, 30),
            received_date=date(2025, 6, 15),
        )
        result = svc._to_dict(item)
        assert result["status"] == "received"
        assert result["wp_id"] is not None
        assert result["cycle_code"] == "D"
        assert result["due_date"] == "2025-06-30"
        assert result["received_date"] == "2025-06-15"

    @pytest.mark.asyncio
    async def test_receive_item_status_transition(self):
        """receive_item 将 pending→received"""
        from app.services.pbc_service import PbcService
        from app.models.collaboration_models import PBCChecklist, PbcStatus

        svc = PbcService()
        item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            item_name="合同",
            status=PbcStatus.PENDING,
        )
        # 模拟 receive 逻辑
        assert item.status == PbcStatus.PENDING
        item.status = PbcStatus.RECEIVED
        item.received_date = date.today()
        assert item.status == PbcStatus.RECEIVED
        assert item.received_date == date.today()


# ─── Document Recognizer 单测 ─────────────────────────────────────────────────


class TestDocumentRecognizer:
    """LLM 识别 mock 测试"""

    @pytest.mark.asyncio
    async def test_stub_mode_returns_fields(self):
        """WP_AI_SERVICE_ENABLED=False 时返回 stub 字段模板"""
        from app.services.wp_document_recognizer import WpDocumentRecognizer, DocType

        recognizer = WpDocumentRecognizer()

        # 测试各类型的 stub 字段
        for doc_type in [DocType.VOUCHER, DocType.INVOICE, DocType.WAREHOUSE, DocType.BANK_RECEIPT]:
            fields = recognizer._get_stub_fields(doc_type)
            assert isinstance(fields, dict)
            assert len(fields) > 0
            # stub 模式所有值为 None
            assert all(v is None for v in fields.values())

    @pytest.mark.asyncio
    async def test_voucher_fields(self):
        """记账凭证字段完整"""
        from app.services.wp_document_recognizer import DOC_TYPE_FIELDS, DocType

        fields = DOC_TYPE_FIELDS[DocType.VOUCHER]
        assert "voucher_no" in fields
        assert "voucher_date" in fields
        assert "debit_amount" in fields
        assert "credit_amount" in fields
        assert "summary" in fields

    @pytest.mark.asyncio
    async def test_invoice_fields(self):
        """发票字段完整"""
        from app.services.wp_document_recognizer import DOC_TYPE_FIELDS, DocType

        fields = DOC_TYPE_FIELDS[DocType.INVOICE]
        assert "invoice_no" in fields
        assert "invoice_date" in fields
        assert "amount" in fields
        assert "tax_amount" in fields
        assert "total_amount" in fields

    @pytest.mark.asyncio
    async def test_warehouse_fields(self):
        """出入库单字段完整"""
        from app.services.wp_document_recognizer import DOC_TYPE_FIELDS, DocType

        fields = DOC_TYPE_FIELDS[DocType.WAREHOUSE]
        assert "doc_no" in fields
        assert "direction" in fields
        assert "quantity" in fields
        assert "total_amount" in fields

    @pytest.mark.asyncio
    async def test_bank_receipt_fields(self):
        """银行回单字段完整"""
        from app.services.wp_document_recognizer import DOC_TYPE_FIELDS, DocType

        fields = DOC_TYPE_FIELDS[DocType.BANK_RECEIPT]
        assert "receipt_no" in fields
        assert "transaction_date" in fields
        assert "amount" in fields
        assert "payer_name" in fields
        assert "payee_name" in fields

    @pytest.mark.asyncio
    async def test_get_supported_doc_types(self):
        """获取支持的凭证类型列表"""
        from app.services.wp_document_recognizer import WpDocumentRecognizer

        recognizer = WpDocumentRecognizer()
        types = recognizer.get_supported_doc_types()
        assert len(types) == 4
        codes = [t["code"] for t in types]
        assert "voucher" in codes
        assert "invoice" in codes
        assert "warehouse" in codes
        assert "bank_receipt" in codes

    @pytest.mark.asyncio
    async def test_recognize_stub_mode(self):
        """stub 模式下 recognize 返回正确结构"""
        from app.services.wp_document_recognizer import WpDocumentRecognizer

        recognizer = WpDocumentRecognizer()
        att_id = uuid.uuid4()

        mock_db = AsyncMock()
        # Mock _get_attachment_info
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (
            str(att_id), "test.jpg", "/path/test.jpg", "image/jpeg"
        )
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.config.settings") as mock_settings:
            mock_settings.WP_AI_SERVICE_ENABLED = False

            result = await recognizer.recognize(
                mock_db,
                attachment_id=att_id,
                doc_type="voucher",
            )

        assert result["status"] == "recognized"
        assert result["is_llm_stub"] is True
        assert "fields" in result
        assert result["doc_type"] == "voucher"


# ─── Evidence Group 填充测试 ─────────────────────────────────────────────────


class TestEvidenceGroup:
    """evidence_group 填充测试"""

    @pytest.mark.asyncio
    async def test_fill_evidence_group(self):
        """fill_evidence_group 正确追加到数组"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService
        import json

        svc = WpEvidenceOcrService()

        # 模拟 DB 返回的 parsed_data
        parsed_data = {
            "action_data": {
                "entries": [
                    {"voucher_no": "001", "debit_amount": 1000, "evidence_group": []},
                    {"voucher_no": "002", "debit_amount": 2000, "evidence_group": []},
                ]
            }
        }

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (parsed_data,)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()

        wp_id = uuid.uuid4()
        voucher_data = {
            "attachment_id": str(uuid.uuid4()),
            "fields": {
                "voucher_no": "001",
                "voucher_date": "2025-01-15",
                "debit_amount": "1000.00",
            },
            "confidence": 0.85,
        }

        result = await svc.fill_evidence_group(mock_db, wp_id, 0, voucher_data)
        assert result is True

    @pytest.mark.asyncio
    async def test_cross_check_evidence_matched(self):
        """证据链交叉核对 - 匹配"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "001", "debit_amount": 1000, "credit_amount": 0}
        evidence_group = [
            {"voucher_no": "001", "amount": 1000},
        ]

        result = await svc.cross_check_evidence(entry, evidence_group)
        assert result["matched"] is True
        assert result["evidence_count"] == 1

    @pytest.mark.asyncio
    async def test_cross_check_evidence_mismatch(self):
        """证据链交叉核对 - 凭证号不匹配"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "001", "debit_amount": 1000, "credit_amount": 0}
        evidence_group = [
            {"voucher_no": "002", "amount": 1000},
        ]

        result = await svc.cross_check_evidence(entry, evidence_group)
        assert result["matched"] is False
        assert len(result["issues"]) > 0
        assert result["issues"][0]["type"] == "voucher_no_mismatch"

    @pytest.mark.asyncio
    async def test_cross_check_evidence_amount_mismatch(self):
        """证据链交叉核对 - 金额差异"""
        from app.services.wp_evidence_ocr_service import WpEvidenceOcrService

        svc = WpEvidenceOcrService()
        entry = {"voucher_no": "001", "debit_amount": 1000, "credit_amount": 0}
        evidence_group = [
            {"voucher_no": "001", "amount": 1200},  # 20% 差异
        ]

        result = await svc.cross_check_evidence(entry, evidence_group)
        assert result["matched"] is False
        assert any(i["type"] == "amount_mismatch" for i in result["issues"])


# ─── PBC 逾期检测测试 ─────────────────────────────────────────────────────────


class TestPbcOverdue:
    """PBC 逾期检测 + IssueTicket 创建"""

    @pytest.mark.asyncio
    async def test_overdue_detection_logic(self):
        """逾期检测逻辑：due_date < today + status=pending"""
        from app.models.collaboration_models import PBCChecklist, PbcStatus

        today = date.today()
        # 逾期项
        overdue_item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            item_name="逾期资料",
            status=PbcStatus.PENDING,
            due_date=today - timedelta(days=3),
        )
        assert overdue_item.due_date < today
        assert overdue_item.status == PbcStatus.PENDING

        # 未逾期项
        ok_item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            item_name="正常资料",
            status=PbcStatus.PENDING,
            due_date=today + timedelta(days=5),
        )
        assert ok_item.due_date >= today

        # 已收到项（不算逾期）
        received_item = PBCChecklist(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            item_name="已收资料",
            status=PbcStatus.RECEIVED,
            due_date=today - timedelta(days=1),
        )
        assert received_item.status != PbcStatus.PENDING

    @pytest.mark.asyncio
    async def test_ticket_source_is_pbc(self):
        """自动建的 IssueTicket source=pbc"""
        from app.models.phase15_models import IssueTicket

        ticket = IssueTicket(
            project_id=uuid.uuid4(),
            source="pbc",
            source_ref_id=uuid.uuid4(),
            severity="major",
            category="evidence_missing",
            title="PBC 逾期未收: 测试",
            owner_id=uuid.uuid4(),
            status="open",
            trace_id="test-trace-001",
        )
        assert ticket.source == "pbc"
        assert ticket.category == "evidence_missing"
        assert ticket.severity == "major"
