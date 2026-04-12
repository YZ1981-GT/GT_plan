"""
AI底稿填充服务单元测试
测试AI辅助底稿填充核心功能
需求覆盖: 3.1-3.6, 9.1, 9.2, 9.5
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.workpaper_fill_service import WorkpaperFillService
from app.models.ai_models import AIContentType, AIContent, ConfidenceLevel, WorkpaperPhase


class TestWorkpaperFillService:
    """测试底稿AI填充服务"""

    @pytest.mark.asyncio
    async def test_generate_analytical_review(self):
        """测试生成分析性复核内容"""
        mock_db = AsyncMock()
        
        with patch.object(WorkpaperFillService, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "summary": "2024年度营业收入较上年增长15%，主要系产品A销量增加所致",
                "key_findings": [
                    "毛利率下降2个百分点，因原材料价格上涨",
                    "应收账款周转天数延长，需关注信用风险",
                    "存货周转加快，运营效率提升",
                ],
                "risk_indicators": [
                    "收入增长与经营活动现金流不匹配",
                    "第四季度收入占比异常偏高",
                ],
                "recommendation": "建议对年末应收账款实施函证程序，对毛利率下降原因做进一步分析",
            }
            
            service = WorkpaperFillService(mock_db)
            
            result = await service.generate_analytical_review(
                project_id=uuid4(),
                company_code="1001",
                year="2024",
            )
            
            assert result is not None
            assert "summary" in result
            assert "key_findings" in result
            assert "risk_indicators" in result
            assert isinstance(result["key_findings"], list)

    @pytest.mark.asyncio
    async def test_create_ai_content(self):
        """测试AI内容创建流程"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        result = await service.create_ai_content(
            workpaper_id=uuid4(),
            content_type=AIContentType.ANALYTICAL_REVIEW,
            ai_content="测试分析内容",
            confidence_score=0.85,
            ai_annotation="基于2024年度财务数据生成的初步分析",
            created_by=uuid4(),
        )
        
        assert result is not None
        assert result.ai_content == "测试分析内容"
        assert result.confidence_score == 0.85
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_accept_ai_content(self):
        """测试接受AI生成的内容"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        content_id = uuid4()
        mock_content = MagicMock(spec=AIContent)
        mock_content.content_id = content_id
        mock_content.status = "pending"
        mock_content.ai_content = "测试内容"
        
        with patch.object(WorkpaperFillService, '_get_content', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_content
            
            service = WorkpaperFillService(mock_db)
            result = await service.accept_content(
                content_id=content_id,
                reviewed_by=uuid4(),
            )
            
            assert result.status == "accepted"

    @pytest.mark.asyncio
    async def test_reject_ai_content(self):
        """测试拒绝AI生成的内容"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        content_id = uuid4()
        mock_content = MagicMock(spec=AIContent)
        mock_content.content_id = content_id
        mock_content.status = "pending"
        
        with patch.object(WorkpaperFillService, '_get_content', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_content
            
            service = WorkpaperFillService(mock_db)
            result = await service.reject_content(
                content_id=content_id,
                rejection_reason="数据不准确，需要核实",
                reviewed_by=uuid4(),
            )
            
            assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_regenerate_content(self):
        """测试重新生成AI内容"""
        mock_db = AsyncMock()
        
        with patch.object(WorkpaperFillService, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "summary": "重新生成的分析内容",
                "key_findings": ["发现新的风险点"],
                "risk_indicators": [],
                "recommendation": "建议扩大抽样范围",
            }
            
            service = WorkpaperFillService(mock_db)
            
            result = await service.regenerate_content(
                content_id=uuid4(),
                feedback="请更关注毛利率分析",
            )
            
            assert result is not None
            mock_llm.assert_called()

    @pytest.mark.asyncio
    async def test_critical_workpaper_gate(self):
        """测试关键底稿pending门控"""
        mock_db = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        # 关键底稿类型
        critical_types = ["收入确认", "资产减值", "或有负债", "关联方交易"]
        
        for wp_type in critical_types:
            has_gate = service._is_critical_workpaper(wp_type)
            assert has_gate == True, f"{wp_type} should be critical"

    @pytest.mark.asyncio
    async def test_stage_transition_gate(self):
        """测试阶段转换门控"""
        mock_db = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        # AI_BLANK -> AI_ANALYSIS 转换需要AI内容
        can_transition = service.can_transition_to_analysis(
            workpaper_id=uuid4(),
            has_ai_content=True,
        )
        assert can_transition == True
        
        # 无AI内容不能转换
        can_transition_no_content = service.can_transition_to_analysis(
            workpaper_id=uuid4(),
            has_ai_content=False,
        )
        assert can_transition_no_content == False

    @pytest.mark.asyncio
    async def test_ai_annotation_persistence(self):
        """测试AI标注持久化"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        annotation = {
            "model_name": "qwen2.5:14b",
            "confidence_score": 0.87,
            "generation_time": "2024-01-15T10:30:00Z",
            "data_sources": ["trial_balance", "general_ledger"],
            "ai_annotation": "基于期初余额和本期发生额计算生成",
        }
        
        result = await service.create_ai_content(
            workpaper_id=uuid4(),
            content_type=AIContentType.ANALYTICAL_REVIEW,
            ai_content="测试内容",
            confidence_score=0.87,
            ai_annotation=str(annotation),
            created_by=uuid4(),
        )
        
        assert result.ai_annotation is not None
        assert "qwen2.5:14b" in result.ai_annotation
        assert "confidence_score" in result.ai_annotation

    @pytest.mark.asyncio
    async def test_confidence_level_classification(self):
        """测试置信度等级分类"""
        service = WorkpaperFillService(AsyncMock())
        
        # 高置信度
        assert service._classify_confidence(0.95) == ConfidenceLevel.HIGH
        # 中置信度
        assert service._classify_confidence(0.75) == ConfidenceLevel.MEDIUM
        # 低置信度需要强制复核
        assert service._classify_confidence(0.50) == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_low_confidence_force_review(self):
        """测试低置信度强制人工复核"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        # 创建低置信度内容
        result = await service.create_ai_content(
            workpaper_id=uuid4(),
            content_type=AIContentType.ANALYTICAL_REVIEW,
            ai_content="测试内容",
            confidence_score=0.45,  # 低置信度
            ai_annotation="低置信度内容",
            created_by=uuid4(),
        )
        
        # 低置信度内容状态应为pending待复核
        assert result.status == "pending"
        assert result.confidence_level == ConfidenceLevel.LOW

    @pytest.mark.asyncio
    async def test_book_data_matching(self):
        """测试账面数据匹配"""
        mock_db = AsyncMock()
        
        service = WorkpaperFillService(mock_db)
        
        # 模拟账面数据
        book_data = {
            "revenue": 1000000,
            "cost": 600000,
            "gross_margin": 0.40,
        }
        
        # AI生成的内容应包含与账面数据的对比
        with patch.object(WorkpaperFillService, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "summary": f"收入{book_data['revenue']}元，毛利率{book_data['gross_margin']*100}%",
                "key_findings": ["毛利率符合行业水平"],
                "risk_indicators": [],
                "recommendation": "建议保持现状",
            }
            
            result = await service.generate_analytical_review(
                project_id=uuid4(),
                company_code="1001",
                year="2024",
            )
            
            assert "1000000" in result["summary"] or "100万" in result["summary"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
