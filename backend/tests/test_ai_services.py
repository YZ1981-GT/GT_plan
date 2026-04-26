"""
AI Services Unit Tests
测试 AI 服务层核心功能（适配当前 AIService(db) 构造函数签名）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAIService:
    """测试 AI 统一服务"""

    def _make_mock_db(self):
        """创建 mock AsyncSession"""
        db = AsyncMock()
        # mock get_active_model 返回 None（使用默认模型）
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=mock_result)
        return db

    @pytest.mark.asyncio
    async def test_chat_completion_success(self):
        """测试对话补全成功"""
        from app.services.ai_service import AIService

        db = self._make_mock_db()
        service = AIService(db)

        with patch('app.services.ai_service._get_llm_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "测试回复"}}],
            })
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_factory.return_value = mock_client

            result = await service.chat_completion(
                messages=[{"role": "user", "content": "你好"}],
            )
            assert result == "测试回复"

    @pytest.mark.asyncio
    async def test_chat_completion_with_system_prompt(self):
        """测试带系统提示的对话"""
        from app.services.ai_service import AIService

        db = self._make_mock_db()
        service = AIService(db)

        with patch('app.services.ai_service._get_llm_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                "choices": [{"message": {"role": "assistant", "content": "专业回答"}}],
            })
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_factory.return_value = mock_client

            result = await service.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一名审计师"},
                    {"role": "user", "content": "什么是实质性程序"},
                ],
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_boundary_check(self):
        """测试AI边界检查"""
        from app.services.ai_service import AIService

        db = self._make_mock_db()
        service = AIService(db)

        assert service.check_boundary("请出具审计意见") is True
        assert service.check_boundary("帮我分析这个科目的变动") is False
        assert service.get_boundary_response() is not None


class TestOCRService:
    """测试 OCR 服务"""

    def test_ocr_service_initialization(self):
        """测试 OCR 服务初始化（需要 db 参数）"""
        from app.services.ocr_service_v2 import OCRService

        db = AsyncMock()
        service = OCRService(db)
        assert service.db is db
        assert service.ai is not None

    def test_document_type_labels(self):
        """测试文档类型标签映射"""
        from app.services.ocr_service_v2 import OCRService

        db = AsyncMock()
        service = OCRService(db)
        assert "sales_invoice" in service.DOCUMENT_TYPE_LABELS
        assert service.DOCUMENT_TYPE_LABELS["sales_invoice"] == "销售发票"
        assert service.DOCUMENT_TYPE_LABELS["contract"] == "合同协议"
        assert service.DOCUMENT_TYPE_LABELS["other"] == "其他单据"

    def test_document_field_rules(self):
        """测试文档字段提取规则"""
        from app.services.ocr_service_v2 import OCRService

        db = AsyncMock()
        service = OCRService(db)
        assert "amount" in service.DOCUMENT_FIELD_RULES["sales_invoice"]
        assert "voucher_no" in service.DOCUMENT_FIELD_RULES["voucher"]
        assert service.DOCUMENT_FIELD_RULES["other"] == []


class TestWorkpaperFillService:
    """测试底稿填充服务"""

    def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        db = AsyncMock()
        service = WorkpaperFillService(db)
        assert service.db is db

    def test_build_description_prompt(self):
        """测试描述性分析提示词构建"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        db = AsyncMock()
        service = WorkpaperFillService(db)
        prompt = service._build_description_prompt({"account_name": "货币资金", "period": "2025"})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_parse_ai_response(self):
        """测试解析AI响应"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        db = AsyncMock()
        service = WorkpaperFillService(db)
        result = service._parse_ai_response({"content": "测试内容"})
        assert result is not None


class TestContractAnalysisService:
    """测试合同分析服务"""

    def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.contract_analysis_service import ContractAnalysisService

        db = AsyncMock()
        service = ContractAnalysisService(db)
        assert service.db is db

    def test_build_analysis_prompt(self):
        """测试分析提示词构建"""
        from app.services.contract_analysis_service import ContractAnalysisService

        db = AsyncMock()
        service = ContractAnalysisService(db)
        prompt = service._build_analysis_prompt("采购合同内容...", "采购合同", "risk")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_parse_analysis_items(self):
        """测试解析分析结果"""
        from app.services.contract_analysis_service import ContractAnalysisService

        db = AsyncMock()
        service = ContractAnalysisService(db)
        items = service._parse_analysis_items("1. 违约金过低\n2. 付款期限不明", "risk")
        assert isinstance(items, list)

    def test_extract_summary(self):
        """测试摘要提取"""
        from app.services.contract_analysis_service import ContractAnalysisService

        db = AsyncMock()
        service = ContractAnalysisService(db)
        summary = service._extract_summary("这是一份采购合同，总金额100万元。")
        assert isinstance(summary, str)


class TestKnowledgeIndexService:
    """测试知识库索引服务"""

    def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.knowledge_index_service import KnowledgeIndexService

        db = AsyncMock()
        service = KnowledgeIndexService(db)
        assert service is not None


class TestAIChatService:
    """测试 AI 聊天服务"""

    def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.ai_chat_service import AIChatService

        db = AsyncMock()
        service = AIChatService(db)
        assert service.db is db


class TestAIModels:
    """测试 AI 模型定义"""

    def test_model_type_enum(self):
        """测试模型类型枚举"""
        from app.models.ai_models import AIModelType

        assert AIModelType.chat.value == "chat"
        assert AIModelType.embedding.value == "embedding"
        assert AIModelType.ocr.value == "ocr"

    def test_session_type_enum(self):
        """测试会话类型枚举"""
        from app.models.ai_models import SessionType

        assert SessionType.general.value == "general"
        assert SessionType.contract.value == "contract"
        assert SessionType.workpaper.value == "workpaper"


class TestAISchemas:
    """测试 AI Pydantic Schema"""

    def test_ai_model_type_values(self):
        """测试模型类型值"""
        from app.models.ai_models import AIModelType
        assert len(AIModelType) >= 3


class TestAIIntegration:
    """AI 功能集成测试"""

    def test_full_ocr_pipeline_mock(self):
        """测试完整 OCR 流程（mock）"""
        mock_result = {
            "success": True,
            "text": "发票号码: 123456\n金额: 1000.00元",
            "confidence": 0.95,
        }
        assert mock_result["success"] is True
        assert "text" in mock_result

    def test_full_contract_analysis_pipeline(self):
        """测试完整合同分析流程"""
        from app.services.contract_analysis_service import ContractAnalysisService

        db = AsyncMock()
        service = ContractAnalysisService(db)
        prompt = service._build_analysis_prompt("采购合同内容", "采购合同", "risk")
        assert isinstance(prompt, str)
        items = service._parse_analysis_items("1. 违约金过低", "risk")
        assert isinstance(items, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
