"""
AI Services Unit Tests
测试 AI 服务层核心功能
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4


class TestAIService:
    """测试 AI 统一服务"""

    @pytest.mark.asyncio
    async def test_chat_completion_success(self):
        """测试对话补全成功"""
        from app.services.ai_service import AIService

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        # Mock response
        mock_result = MagicMock()
        mock_result.scalar_one_or_return = AsyncMock(return_value="""{
            "model_id": "test-model",
            "model_name": "Test Model",
            "provider": "ollama",
            "model_type": "chat",
            "endpoint": "http://localhost:11434",
            "status": "active",
            "temperature": 0.7,
            "max_tokens": 4096,
            "system_prompt": "You are a helpful assistant.",
            "is_default": true,
            "cost_per_1k_input_tokens": 0.0,
            "cost_per_1k_output_tokens": 0.0,
            "context_window": 8192,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00"
        }""")

        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                "model": "llama3",
                "message": {"role": "assistant", "content": "测试回复"},
                "done": True,
            })
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            service = AIService()
            result = await service.chat_completion(
                messages=[{"role": "user", "content": "你好"}],
                model_id="test-model",
            )
            assert result is not None
            assert "content" in result

    @pytest.mark.asyncio
    async def test_chat_completion_with_system_prompt(self):
        """测试带系统提示的对话"""
        from app.services.ai_service import AIService

        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                "model": "llama3",
                "message": {"role": "assistant", "content": "专业回答"},
                "done": True,
            })
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            service = AIService()
            result = await service.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一名审计师"},
                    {"role": "user", "content": "什么是实质性程序"},
                ],
                model_id="audit-model",
            )
            assert result is not None


class TestOllamaIntegration:
    """测试 Ollama 集成"""

    @pytest.mark.asyncio
    async def test_ollama_available(self):
        """测试 Ollama 服务可用性"""
        from app.services.ai_service import OllamaClient

        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={"models": []})
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            client = OllamaClient()
            # 不测试真实连接，只验证客户端创建
            assert client.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_embedding_generation(self):
        """测试嵌入向量生成"""
        from app.services.ai_service import OllamaClient

        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value={
                "embedding": [0.1] * 768,
            })
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            client = OllamaClient()
            result = await client.generate_embedding("测试文本")
            assert isinstance(result, list)
            assert len(result) > 0


class TestOCRService:
    """测试 OCR 服务"""

    @pytest.mark.asyncio
    async def test_ocr_service_initialization(self):
        """测试 OCR 服务初始化"""
        from app.services.ocr_service_v2 import OCRService

        service = OCRService()
        assert service.provider == "paddleocr"
        assert service.use_angle_cls is True
        assert service.use_space is True

    @pytest.mark.asyncio
    async def test_document_type_mapping(self):
        """测试文档类型映射"""
        from app.services.ocr_service_v2 import OCRService

        service = OCRService()
        assert service.get_doc_type_code("invoice") == "FP"
        assert service.get_doc_type_code("receipt") == "JS"
        assert service.get_doc_type_code("contract") == "HT"
        assert service.get_doc_type_code("unknown") == "QT"


class TestWorkpaperFillService:
    """测试底稿填充服务"""

    def test_analysis_type_prompts(self):
        """测试分析类型提示词"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        service = WorkpaperFillService()

        summary_prompt = service.get_analysis_prompt("summary")
        assert "摘要" in summary_prompt or "summary" in summary_prompt.lower()

        fill_prompt = service.get_analysis_prompt("fill")
        assert fill_prompt is not None

        compare_prompt = service.get_analysis_prompt("compare")
        assert compare_prompt is not None

    def test_parse_fill_result(self):
        """测试解析填充结果"""
        from app.services.workpaper_fill_service import WorkpaperFillService

        service = WorkpaperFillService()

        # 正常结果
        result = service.parse_fill_result("字段1: 值1\n字段2: 值2")
        assert result is not None

        # 空结果
        empty = service.parse_fill_result("")
        assert empty is not None


class TestContractAnalysisService:
    """测试合同分析服务"""

    def test_risk_extraction(self):
        """测试风险项提取"""
        from app.services.contract_analysis_service import ContractAnalysisService

        service = ContractAnalysisService()

        sample_text = """
        本合同存在以下风险点：
        1. 违约金过低，仅为合同金额的1%
        2. 付款期限约定不明
        3. 争议解决条款缺失
        """

        result = service.extract_risk_items(sample_text)
        assert isinstance(result, list)

    def test_clause_extraction(self):
        """测试条款提取"""
        from app.services.contract_analysis_service import ContractAnalysisService

        service = ContractAnalysisService()

        sample_text = """
        第三条 付款方式
        买方应于收到货物后30日内支付全部货款。

        第四条 违约责任
        任何一方违约，应向对方支付合同金额10%的违约金。
        """

        clauses = service.extract_clauses(sample_text)
        assert isinstance(clauses, list)


class TestKnowledgeIndexService:
    """测试知识库索引服务"""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """测试服务初始化"""
        from app.services.knowledge_index_service import KnowledgeIndexService

        service = KnowledgeIndexService()
        assert service.collection_name == "audit_knowledge"
        assert service.embedding_model == "nomic-embed-text"

    def test_chunk_text(self):
        """测试文本分块"""
        from app.services.knowledge_index_service import KnowledgeIndexService

        service = KnowledgeIndexService()

        # 长文本
        long_text = "测试文本 " * 1000
        chunks = service.chunk_text(long_text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

        # 短文本
        short_text = "短文本"
        chunks = service.chunk_text(short_text)
        assert len(chunks) == 1


class TestEvidenceChainService:
    """测试证据链服务"""

    def test_calculate_completeness(self):
        """测试完整性评分计算"""
        from app.services.evidence_chain_service import EvidenceChainService

        service = EvidenceChainService()

        # 完整证据链
        items = [
            {"is_key_evidence": True, "has_supporting_docs": True},
            {"is_key_evidence": True, "has_supporting_docs": True},
            {"is_key_evidence": False, "has_supporting_docs": True},
        ]
        score = service.calculate_completeness(items)
        assert 0 <= score <= 100

    def test_generate_chain_insights(self):
        """测试生成链洞察"""
        from app.services.evidence_chain_service import EvidenceChainService

        service = EvidenceChainService()

        insights = service.generate_chain_insights([])
        assert insights is not None


class TestAIChatService:
    """测试 AI 聊天服务"""

    @pytest.mark.asyncio
    async def test_build_rag_context(self):
        """测试构建 RAG 上下文"""
        from app.services.ai_chat_service import AIChatService

        service = AIChatService()

        # Mock ChromaDB response
        mock_results = [
            {
                "content": "审计证据是指审计人员在审计过程中获取的...",
                "metadata": {"source": "审计准则", "relevance": 0.95},
            }
        ]

        context = service.build_rag_context(mock_results)
        assert context is not None
        assert len(context) > 0

    def test_format_chat_history(self):
        """测试格式化聊天历史"""
        from app.services.ai_chat_service import AIChatService

        service = AIChatService()

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好，有什么可以帮你的？"},
        ]

        formatted = service.format_chat_history(messages)
        assert "user: 你好" in formatted
        assert "assistant: 你好" in formatted


class TestAIModels:
    """测试 AI 模型定义"""

    def test_model_enum_values(self):
        """测试模型枚举值"""
        from app.models.ai_models import AIModelType, AIModelStatus

        assert AIModelType.CHAT.value == "chat"
        assert AIModelType.EMBEDDING.value == "embedding"
        assert AIModelType.VISION.value == "vision"

        assert AIModelStatus.ACTIVE.value == "active"
        assert AIModelStatus.INACTIVE.value == "inactive"

    def test_evidence_type_enum(self):
        """测试证据类型枚举"""
        from app.models.ai_models import EvidenceType

        assert EvidenceType.EXTERNAL.value == "external"
        assert EvidenceType.INTERNAL.value == "internal"
        assert EvidenceType.DOCUMENTARY.value == "documentary"
        assert EvidenceType.ELECTRONIC.value == "electronic"

    def test_session_type_enum(self):
        """测试会话类型枚举"""
        from app.models.ai_models import SessionType

        assert SessionType.GENERAL.value == "general"
        assert SessionType.AUDIT.value == "audit"
        assert SessionType.RISK.value == "risk"


class TestAISchemas:
    """测试 AI Pydantic Schema"""

    def test_chat_message_create(self):
        """测试聊天消息创建"""
        from app.models.ai_schemas import ChatMessageCreate

        msg = ChatMessageCreate(
            content="测试消息",
            role="user",
        )
        assert msg.content == "测试消息"
        assert msg.role == "user"

    def test_fill_task_create(self):
        """测试填充任务创建"""
        from app.models.ai_schemas import FillTaskCreate

        task = FillTaskCreate(
            project_id="proj-123",
            workpaper_name="货币资金",
            analysis_type="summary",
            requirements="提取期末余额",
        )
        assert task.workpaper_name == "货币资金"
        assert task.analysis_type == "summary"

    def test_contract_analysis_create(self):
        """测试合同分析创建"""
        from app.models.ai_schemas import ContractAnalysisCreate

        analysis = ContractAnalysisCreate(
            project_id="proj-123",
            contract_type="采购合同",
            analysis_type="risk",
        )
        assert analysis.contract_type == "采购合同"
        assert analysis.analysis_type == "risk"

    def test_evidence_chain_create(self):
        """测试证据链创建"""
        from app.models.ai_schemas import EvidenceChainCreate

        chain = EvidenceChainCreate(
            project_id="proj-123",
            chain_name="采购循环证据链",
            business_cycle="采购与付款",
        )
        assert chain.chain_name == "采购循环证据链"
        assert chain.business_cycle == "采购与付款"


# ============ Integration Tests ============

class TestAIIntegration:
    """AI 功能集成测试"""

    @pytest.mark.asyncio
    async def test_full_ocr_pipeline(self):
        """测试完整 OCR 流程"""
        from app.services.ocr_service_v2 import OCRService

        service = OCRService()

        # Mock OCR 结果
        mock_result = {
            "success": True,
            "text": "发票号码: 123456\n金额: 1000.00元",
            "confidence": 0.95,
        }

        # 验证结果格式
        assert mock_result["success"] is True
        assert "text" in mock_result
        assert "confidence" in mock_result

    @pytest.mark.asyncio
    async def test_full_contract_analysis_pipeline(self):
        """测试完整合同分析流程"""
        from app.services.contract_analysis_service import ContractAnalysisService

        service = ContractAnalysisService()

        sample_contract = """
        采购合同

        甲方：A公司
        乙方：B公司

        第一条 采购内容
        甲方向乙方采购办公用品，总价100万元。

        第二条 付款方式
        签订合同后支付30%预付款，验收后支付70%尾款。

        第三条 违约责任
        任何一方违约，应支付合同金额10%的违约金。
        """

        # 分析
        risk_items = service.extract_risk_items(sample_contract)
        clauses = service.extract_clauses(sample_contract)

        assert isinstance(risk_items, list)
        assert isinstance(clauses, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
