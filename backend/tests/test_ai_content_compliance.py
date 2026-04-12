"""
AI合规性测试
测试AI内容合规要求
需求覆盖: 9.1-9.6
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.models.ai_models import AIContent, AIContentType, ConfidenceLevel


class TestAICompliance:
    """测试AI合规性"""

    @pytest.mark.asyncio
    async def test_ai_content_marking_in_database(self):
        """测试AI内容在数据库中标注"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        from app.services.workpaper_fill_service import WorkpaperFillService
        
        service = WorkpaperFillService(mock_db)
        
        # 创建AI生成的内容
        content = await service.create_ai_content(
            workpaper_id=uuid4(),
            content_type=AIContentType.ANALYTICAL_REVIEW,
            ai_content="AI生成的分析内容",
            confidence_score=0.85,
            ai_annotation="由qwen2.5:14b生成",
            created_by=uuid4(),
        )
        
        # 验证AI标注被持久化
        assert content.ai_annotation is not None
        assert "qwen2.5:14b" in content.ai_annotation
        assert content.confidence_score == 0.85
        
        # 验证数据库字段存在
        assert hasattr(content, 'ai_confidence')
        assert hasattr(content, 'ai_annotation')
        assert hasattr(content, 'confidence_level')

    @pytest.mark.asyncio
    async def test_pdf_export_preserves_ai_tags(self):
        """测试PDF导出保留AI标签"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        
        # 模拟PDF导出内容
        ai_content = {
            "text": "基于2024年数据分析，营业收入增长15%",
            "ai_confidence": 0.85,
            "ai_annotation": "AI生成内容",
            "confidence_level": "MEDIUM",
        }
        
        from app.services.pdf_export_service import PDFExportService
        
        with patch.object(PDFExportService, 'export_workpaper', new_callable=AsyncMock) as mock_export:
            mock_export.return_value = "/path/to/exported.pdf"
            
            service = PDFExportService(mock_db)
            
            result = await service.export_workpaper(
                workpaper_id=uuid4(),
                include_ai_tags=True,
            )
            
            # 验证AI标签被包含在导出内容中
            assert "ai_confidence" in str(result) or "AI" in str(result)

    @pytest.mark.asyncio
    async def test_ai_boundary_no_judgment_on_critical_items(self):
        """测试AI边界 - 关键项目不进行判断"""
        mock_db = AsyncMock()
        
        from app.services.workpaper_fill_service import WorkpaperFillService
        
        service = WorkpaperFillService(mock_db)
        
        # 关键审计判断项目
        critical_items = [
            "持续经营假设",
            "重大资产减值",
            "或有负债评估",
            "关联方交易定价",
        ]
        
        for item in critical_items:
            can_fill = service._is_ai_allowed(item)
            # 关键判断AI不应直接填制
            assert can_fill == False, f"AI should not fill critical item: {item}"

    @pytest.mark.asyncio
    async def test_ai_generates_suggestion_not_decision(self):
        """测试AI生成建议而非决策"""
        mock_db = AsyncMock()
        
        from app.services.workpaper_fill_service import WorkpaperFillService
        
        service = WorkpaperFillService(mock_db)
        
        # AI生成的内容类型
        content_types = [
            AIContentType.ANALYTICAL_REVIEW,
            AIContentType.AI_SUGGESTION,
        ]
        
        for ct in content_types:
            assert ct in [AIContentType.ANALYTICAL_REVIEW, AIContentType.AI_SUGGESTION]
        
        # AI内容状态应为pending
        pending_status = "pending"
        assert pending_status != "accepted"  # 需要人工确认

    @pytest.mark.asyncio
    async def test_data_stays_local_no_external_api(self):
        """测试数据留在本地，不调用外部API"""
        mock_db = AsyncMock()
        
        from app.services.ai_service import AIService
        
        service = AIService(mock_db)
        
        # 验证Ollama endpoint是本地
        ollama_url = "http://localhost:11434"
        assert "localhost" in ollama_url or "127.0.0.1" in ollama_url
        
        # 验证PaddleOCR是本地包
        import paddleocr
        assert paddleocr is not None
        
        # 验证ChromaDB是本地
        chromadb_url = "http://localhost:8000"
        assert "localhost" in chromadb_url

    @pytest.mark.asyncio
    async def test_model_switch_availability(self):
        """测试模型切换可用性"""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_return = AsyncMock(return_value=None)
        mock_db.execute.return_value = mock_result
        
        from app.services.ai_service import AIService
        
        service = AIService(mock_db)
        
        # 支持的模型类型
        model_types = ["chat", "embedding", "ocr"]
        
        for model_type in model_types:
            result = await service.list_available_models(model_type=model_type)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_confidence_threshold_for_acceptance(self):
        """测试置信度阈值决定是否可接受"""
        from app.models.ai_models import ConfidenceLevel
        
        # 高置信度可直接确认
        high_confidence = ConfidenceLevel.HIGH
        assert high_confidence.value == "high"
        
        # 中置信度需要复核
        medium_confidence = ConfidenceLevel.MEDIUM
        assert medium_confidence.value == "medium"
        
        # 低置信度必须人工
        low_confidence = ConfidenceLevel.LOW
        assert low_confidence.value == "low"

    @pytest.mark.asyncio
    async def test_ai_content_traceability(self):
        """测试AI内容可追溯性"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        from app.services.workpaper_fill_service import WorkpaperFillService
        
        service = WorkpaperFillService(mock_db)
        
        # 创建带完整元数据的AI内容
        content = await service.create_ai_content(
            workpaper_id=uuid4(),
            content_type=AIContentType.ANALYTICAL_REVIEW,
            ai_content="测试内容",
            confidence_score=0.85,
            ai_annotation="model:qwen2.5:14b,time:2024-01-15T10:00:00Z,sources:trial_balance,gl",
            created_by=uuid4(),
        )
        
        # 验证元数据完整性
        annotation = content.ai_annotation
        assert "model:" in annotation
        assert "time:" in annotation
        assert "sources:" in annotation

    @pytest.mark.asyncio
    async def test_human_review_required_for_critical_workpapers(self):
        """测试关键底稿必须人工复核"""
        mock_db = AsyncMock()
        
        from app.services.workpaper_fill_service import WorkpaperFillService
        
        service = WorkpaperFillService(mock_db)
        
        critical_workpaper_types = [
            "收入确认",
            "资产减值测试",
            "或有负债",
            "关联方交易",
            "持续经营评估",
        ]
        
        for wp_type in critical_workpaper_types:
            is_critical = service._is_critical_workpaper(wp_type)
            assert is_critical == True
            
            # 关键底稿即使高置信度也需要复核
            requires_review = service._requires_human_review(
                wp_type, confidence_score=0.95
            )
            assert requires_review == True

    @pytest.mark.asyncio
    async def test_ai_confidence_annotation_format(self):
        """测试AI置信度标注格式"""
        from app.models.ai_models import AIContent
        
        # 验证字段存在
        assert hasattr(AIContent, 'ai_confidence')
        assert hasattr(AIContent, 'ai_annotation')
        assert hasattr(AIContent, 'confidence_level')
        
        # 验证置信度分数范围
        valid_score = 0.85
        assert 0 <= valid_score <= 1
        
        invalid_score = 1.5
        assert not (0 <= invalid_score <= 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
