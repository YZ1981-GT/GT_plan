"""
OCR Service Unit Tests — Task 24.2
Test OCR service methods with mocked OCR responses.
Test document type detection and field extraction from different document types.

Requirements: 2.1-2.7
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from uuid import uuid4

from app.services.ocr_service_v2 import OCRService, _extract_text_from_result
from app.models.ai_models import DocumentType, RecognitionStatus, MatchResult


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


class TestOCRServiceRecognize:
    """Test OCRService.recognize_single()"""

    @pytest.mark.asyncio
    async def test_recognize_single_success(self, mock_db_session):
        """Successful OCR recognition returns items and full text."""
        service = OCRService(mock_db_session)

        # PaddleOCR returns: [[line1, line2, ...]] where each line is [bbox, (text, confidence)]
        mock_ocr_result = [
            [
                ([[0, 0], [100, 0], [100, 20], [0, 20]], ("发票号码: 123456", 0.95)),
                ([[0, 25], [150, 25], [150, 45], [0, 45]], ("金额: ¥10,000.00", 0.92)),
            ]
        ]

        with patch(
            "app.services.ocr_service_v2._get_ocr_engine"
        ) as mock_engine, patch(
            "asyncio.get_event_loop"
        ) as mock_loop:
            mock_engine.return_value.ocr.return_value = mock_ocr_result
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=mock_ocr_result
            )

            result = await service.recognize_single("/fake/path/invoice.jpg")

        assert result["success"] is True
        assert "items" in result
        assert "full_text" in result
        assert "stats" in result
        assert result["stats"]["total_lines"] == 2
        assert result["stats"]["avg_confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_recognize_single_empty_image(self, mock_db_session):
        """OCR on empty image returns empty items."""
        service = OCRService(mock_db_session)

        with patch(
            "app.services.ocr_service_v2._get_ocr_engine"
        ) as mock_engine, patch(
            "asyncio.get_event_loop"
        ) as mock_loop:
            mock_engine.return_value.ocr.return_value = []
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=[]
            )

            result = await service.recognize_single("/fake/empty.jpg")

        assert result["success"] is True
        assert result["items"] == []
        assert result["full_text"] == ""

    @pytest.mark.asyncio
    async def test_recognize_single_failure(self, mock_db_session):
        """OCR failure returns success=False with error."""
        service = OCRService(mock_db_session)

        with patch(
            "app.services.ocr_service_v2._get_ocr_engine"
        ) as mock_engine, patch(
            "asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                side_effect=Exception("Image read error")
            )

            result = await service.recognize_single("/fake/corrupt.jpg")

        assert result["success"] is False
        assert "error" in result


class TestOCRServiceClassify:
    """Test OCRService.classify_document()"""

    @pytest.mark.asyncio
    async def test_classify_sales_invoice(self, mock_db_session):
        """Classifies sales invoice correctly."""
        service = OCRService(mock_db_session)

        ocr_text = (
            "增值税发票\n销售方: A公司\n购买方: B公司\n"
            "金额: 10,000.00元\n税额: 1,300.00元\n"
            "价税合计: 11,300.00元"
        )

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_model.model_name = "qwen2.5:7b"
            mock_active.return_value = mock_model
            mock_chat.return_value = "sales_invoice"

            result = await service.classify_document(ocr_text)

        assert result == "sales_invoice"

    @pytest.mark.asyncio
    async def test_classify_purchase_invoice(self, mock_db_session):
        """Classifies purchase invoice correctly."""
        service = OCRService(mock_db_session)

        ocr_text = (
            "增值税专用发票\n销售方: 供应商公司\n购买方: 客户公司\n"
            "金额: 50,000.00元\n税额: 6,500.00元"
        )

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = "purchase_invoice"

            result = await service.classify_document(ocr_text)

        assert result == "purchase_invoice"

    @pytest.mark.asyncio
    async def test_classify_bank_receipt(self, mock_db_session):
        """Classifies bank receipt correctly."""
        service = OCRService(mock_db_session)

        ocr_text = (
            "银行收款回单\n收款人: ABC公司\n"
            "付款人: XYZ公司\n交易金额: 100,000.00元\n"
            "摘要: 货款"
        )

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = "bank_receipt"

            result = await service.classify_document(ocr_text)

        assert result == "bank_receipt"

    @pytest.mark.asyncio
    async def test_classify_empty_text_defaults_to_other(self, mock_db_session):
        """Empty OCR text defaults to 'other' type."""
        service = OCRService(mock_db_session)

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model

            result = await service.classify_document("")

        assert result == "other"

    @pytest.mark.asyncio
    async def test_classify_unknown_defaults_to_other(self, mock_db_session):
        """LLM returns unknown type defaults to 'other'."""
        service = OCRService(mock_db_session)

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = "some_random_type"

            result = await service.classify_document("random text that doesn't match")

        assert result == "other"


class TestOCRServiceFieldExtraction:
    """Test OCRService.extract_fields()"""

    @pytest.mark.asyncio
    async def test_extract_fields_sales_invoice(self, mock_db_session):
        """Extracts structured fields from sales invoice."""
        service = OCRService(mock_db_session)

        ocr_text = (
            "发票号码: FP12345678\n"
            "购买方: ABC科技有限公司\n"
            "金额: 100,000.00\n"
            "税额: 13,000.00\n"
            "开票日期: 2024-01-15"
        )

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = (
                '[{"field_name":"invoice_no","field_value":"FP12345678","confidence":0.98},'
                '{"field_name":"buyer_name","field_value":"ABC科技有限公司","confidence":0.95},'
                '{"field_name":"amount","field_value":"100000.00","confidence":0.92}]'
            )

            result = await service.extract_fields(ocr_text, "sales_invoice")

        assert len(result) == 3
        assert result[0]["field_name"] == "invoice_no"
        assert result[0]["confidence_score"] == 0.98

    @pytest.mark.asyncio
    async def test_extract_fields_bank_receipt(self, mock_db_session):
        """Extracts structured fields from bank receipt."""
        service = OCRService(mock_db_session)

        ocr_text = (
            "交易日期: 2024-01-20\n"
            "对方户名: XYZ公司\n"
            "交易金额: 50,000.00元\n"
            "摘要: 货款"
        )

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = (
                '[{"field_name":"transaction_date","field_value":"2024-01-20","confidence":0.99},'
                '{"field_name":"counterparty_name","field_value":"XYZ公司","confidence":0.97},'
                '{"field_name":"amount","field_value":"50000.00","confidence":0.93}]'
            )

            result = await service.extract_fields(ocr_text, "bank_receipt")

        assert len(result) == 3
        field_names = [f["field_name"] for f in result]
        assert "transaction_date" in field_names
        assert "counterparty_name" in field_names

    @pytest.mark.asyncio
    async def test_extract_fields_invalid_json_fallback(self, mock_db_session):
        """Invalid LLM response returns empty list gracefully."""
        service = OCRService(mock_db_session)

        with patch.object(
            service.ai, "get_active_model", new_callable=AsyncMock
        ) as mock_active, patch.object(
            service.ai, "chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_model = MagicMock()
            mock_active.return_value = mock_model
            mock_chat.return_value = "This is not JSON output"

            result = await service.extract_fields("some text", "sales_invoice")

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_fields_empty_doc_type(self, mock_db_session):
        """Unknown document type returns empty fields list."""
        service = OCRService(mock_db_session)

        result = await service.extract_fields("some text", "unknown_type")

        assert result == []


class TestOCRServiceBatch:
    """Test OCRService.batch_recognize() and get_task_status()"""

    @pytest.mark.asyncio
    async def test_batch_recognize_returns_task_id(self, mock_db_session):
        """batch_recognize returns a task_id string."""
        service = OCRService(mock_db_session)

        file_paths = ["/path/to/doc1.jpg", "/path/to/doc2.jpg"]

        with patch(
            "app.services.ocr_service_v2._batch_recognize_sync"
        ) as mock_sync, patch(
            "asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock()

            task_id = await service.batch_recognize(
                project_id=uuid4(),
                file_paths=file_paths,
                user_id=uuid4(),
            )

        assert isinstance(task_id, str)
        assert len(task_id) > 0

    @pytest.mark.asyncio
    async def test_get_task_status_pending(self, mock_db_session):
        """get_task_status returns correct status for pending task."""
        service = OCRService(mock_db_session)

        # Manually insert a task
        from app.services.ocr_service_v2 import _task_status

        task_id = "test-task-123"
        _task_status[task_id] = {
            "status": "pending",
            "total": 5,
            "processed": 0,
            "failed": 0,
            "errors": [],
        }

        result = await service.get_task_status(task_id)

        assert result["status"] == "pending"
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, mock_db_session):
        """get_task_status returns not_found for unknown task."""
        service = OCRService(mock_db_session)

        result = await service.get_task_status("nonexistent-task-id")

        assert result["status"] == "not_found"


class TestExtractTextFromResult:
    """Test the _extract_text_from_result helper"""

    def test_extract_text_from_result_normal(self):
        """Normal PaddleOCR result extracts items correctly."""
        # PaddleOCR returns [[line1, line2, ...]] where each line is [bbox, (text, confidence)]
        paddle_result = [
            [
                ([[0, 0], [100, 0], [100, 20], [0, 20]], ("发票号: 123", 0.95)),
                ([[0, 10], [100, 10], [100, 30], [0, 30]], ("金额: 1000", 0.92)),
            ]
        ]

        items = _extract_text_from_result(paddle_result)

        assert len(items) == 2
        assert items[0]["text"] == "发票号: 123"
        assert items[0]["confidence"] == 0.95
        assert items[1]["text"] == "金额: 1000"
        assert items[1]["confidence"] == 0.92

    def test_extract_text_from_result_empty(self):
        """Empty result returns empty list."""
        assert _extract_text_from_result(None) == []
        assert _extract_text_from_result([]) == []

    def test_extract_text_from_result_malformed(self):
        """Malformed items are skipped gracefully."""
        paddle_result = [[None], [{"bbox": None}]]
        items = _extract_text_from_result(paddle_result)
        assert items == []


class TestDocumentTypeMapping:
    """Test document type mapping constants"""

    def test_document_field_rules_has_all_types(self):
        """DOCUMENT_FIELD_RULES has entries for all 12 types."""
        service = OCRService.__new__(OCRService)

        expected_types = [
            "sales_invoice",
            "purchase_invoice",
            "bank_receipt",
            "bank_statement",
            "outbound_order",
            "inbound_order",
            "logistics_order",
            "voucher",
            "tax_return",
            "contract",
            "bank_reconciliation",
            "other",
        ]

        for doc_type in expected_types:
            assert doc_type in service.DOCUMENT_FIELD_RULES

    def test_document_type_labels_has_all_types(self):
        """DOCUMENT_TYPE_LABELS has Chinese labels for all types."""
        service = OCRService.__new__(OCRService)

        assert service.DOCUMENT_TYPE_LABELS["sales_invoice"] == "销售发票"
        assert service.DOCUMENT_TYPE_LABELS["purchase_invoice"] == "采购发票"
        assert service.DOCUMENT_TYPE_LABELS["bank_receipt"] == "银行收付款回单"
        assert service.DOCUMENT_TYPE_LABELS["bank_statement"] == "银行对账单"
        assert service.DOCUMENT_TYPE_LABELS["contract"] == "合同协议"
        assert service.DOCUMENT_TYPE_LABELS["other"] == "其他单据"


class TestProcessImageBytes:
    """Test the standalone process_image_bytes function"""

    @pytest.mark.asyncio
    async def test_process_image_bytes_success(self):
        """process_image_bytes returns OCR result for image bytes."""
        with patch(
            "app.services.ocr_service_v2._get_ocr_engine"
        ) as mock_engine, patch(
            "asyncio.get_event_loop"
        ) as mock_loop, patch(
            "app.services.ocr_service_v2.base64"
        ):
            from app.services.ocr_service_v2 import process_image_bytes

            mock_ocr_result = [
                [
                    ([[0, 0], [100, 0]], ("测试文本", 0.95)),
                ]
            ]
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=mock_ocr_result
            )

            result = await process_image_bytes(
                b"fake_image_bytes", ocr_type="测试"
            )

        assert result["success"] is True
        assert "items" in result
        assert "stats" in result

    @pytest.mark.asyncio
    async def test_process_image_bytes_failure(self):
        """process_image_bytes handles failure gracefully."""
        from app.services.ocr_service_v2 import process_image_bytes

        with patch(
            "app.services.ocr_service_v2._get_ocr_engine"
        ) as mock_engine, patch(
            "asyncio.get_event_loop"
        ) as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                side_effect=Exception("decode error")
            )

            result = await process_image_bytes(b"bad_bytes")

        assert result["success"] is False
        assert "error" in result
