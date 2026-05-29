"""
合同分析服务单元测试
测试合同分析核心功能
需求覆盖: 4.1-4.6
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime
from uuid import uuid4

from app.services.contract_analysis_service import ContractAnalysisService
from app.models.ai_models import (
    ContractType, ContractAnalysisStatus, ClauseType, ContractLinkType,
    RiskLevel, AIAnalysisReport, AnalysisReportStatus,
    Contract, ContractExtracted, ContractWPLink,
)


class TestContractAnalysisService:
    """测试合同分析服务"""

    @pytest.mark.asyncio
    async def test_analyze_contract_basic(self):
        """测试基础合同分析"""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_ai_service = MagicMock()
        mock_ai_service.chat = AsyncMock(return_value={
            "content": "合同分析结果：该合同为技术服务合同，金额50万元。"
        })

        service = ContractAnalysisService(mock_db)

        result = await service.analyze_contract(
            project_id=uuid4(),
            contract_text="甲乙双方签订技术服务合同，金额50万元",
            contract_type="service",
            analysis_type="full",
            ai_service=mock_ai_service,
        )

        assert result is not None
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_analyze_contract_failure(self):
        """测试合同分析失败场景"""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_ai_service = MagicMock()
        mock_ai_service.chat = AsyncMock(side_effect=Exception("LLM unavailable"))

        service = ContractAnalysisService(mock_db)

        with pytest.raises(Exception, match="LLM unavailable"):
            await service.analyze_contract(
                project_id=uuid4(),
                contract_text="测试合同文本",
                contract_type="sales",
                analysis_type="full",
                ai_service=mock_ai_service,
            )

    @pytest.mark.asyncio
    async def test_batch_analyze(self):
        """测试批量合同分析 - 返回 task_id"""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock contract query results
        mock_contract = MagicMock()
        mock_contract.contract_type = ContractType.sales
        mock_contract.contract_text = "测试合同"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContractAnalysisService(mock_db)

        contract_ids = [uuid4() for _ in range(3)]

        with patch('app.services.ai_service.AIService') as mock_ai_cls:
            mock_ai_instance = MagicMock()
            mock_ai_instance.chat = AsyncMock(return_value={"content": "分析结果"})
            mock_ai_cls.return_value = mock_ai_instance

            result = await service.batch_analyze(
                project_id=uuid4(),
                contract_ids=contract_ids,
                analysis_type="full",
            )

        # batch_analyze returns a task_id string
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_link_to_workpaper(self):
        """测试合同与底稿关联"""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock contract exists
        mock_contract = MagicMock()
        mock_contract.id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContractAnalysisService(mock_db)

        contract_id = uuid4()
        workpaper_id = uuid4()

        result = await service.link_to_workpaper(
            contract_id=contract_id,
            workpaper_id=workpaper_id,
            link_type="revenue_recognition",
            description="合同为收入确认底稿的支持性证据",
        )

        assert result is not None
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_link_to_workpaper_not_found(self):
        """测试关联不存在的合同"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContractAnalysisService(mock_db)

        with pytest.raises(ValueError, match="not found"):
            await service.link_to_workpaper(
                contract_id=uuid4(),
                workpaper_id=uuid4(),
                link_type="revenue_recognition",
            )

    @pytest.mark.asyncio
    async def test_get_report(self):
        """测试获取分析报告"""
        mock_db = AsyncMock()
        mock_report = MagicMock()
        mock_report.id = uuid4()
        mock_report.status = AnalysisReportStatus.completed
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_report
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContractAnalysisService(mock_db)

        result = await service.get_report(mock_report.id)
        assert result is not None
        assert result.status == AnalysisReportStatus.completed

    @pytest.mark.asyncio
    async def test_get_report_items(self):
        """测试获取分析报告项目"""
        mock_db = AsyncMock()
        mock_items = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=mock_items))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ContractAnalysisService(mock_db)

        result = await service.get_report_items(uuid4())
        assert len(result) == 2

    def test_contract_type_enum_values(self):
        """测试合同类型枚举值"""
        assert ContractType.sales.value == "sales"
        assert ContractType.purchase.value == "purchase"
        assert ContractType.service.value == "service"
        assert ContractType.lease.value == "lease"
        assert ContractType.loan.value == "loan"
        assert ContractType.guarantee.value == "guarantee"
        assert ContractType.other.value == "other"

    def test_contract_analysis_status_enum(self):
        """测试合同分析状态枚举"""
        assert ContractAnalysisStatus.pending.value == "pending"
        assert ContractAnalysisStatus.analyzing.value == "analyzing"
        assert ContractAnalysisStatus.completed.value == "completed"
        assert ContractAnalysisStatus.failed.value == "failed"

    def test_clause_type_enum(self):
        """测试条款类型枚举"""
        assert ClauseType.payment_terms.value == "payment_terms"
        assert ClauseType.penalty.value == "penalty"
        assert ClauseType.guarantee.value == "guarantee"
        assert ClauseType.special_terms.value == "special_terms"
        assert ClauseType.amount.value == "amount"

    def test_contract_link_type_enum(self):
        """测试合同关联类型枚举"""
        assert ContractLinkType.revenue_recognition.value == "revenue_recognition"
        assert ContractLinkType.cutoff_test.value == "cutoff_test"
        assert ContractLinkType.contingent_liability.value == "contingent_liability"
        assert ContractLinkType.related_party.value == "related_party"

    def test_risk_level_enum(self):
        """测试风险等级枚举"""
        assert RiskLevel.high.value == "high"
        assert RiskLevel.medium.value == "medium"
        assert RiskLevel.low.value == "low"

    @pytest.mark.asyncio
    async def test_build_analysis_prompt(self):
        """测试分析提示词构建"""
        mock_db = AsyncMock()
        service = ContractAnalysisService(mock_db)

        prompt = service._build_analysis_prompt(
            contract_text="测试合同文本",
            contract_type="sales",
            analysis_type="full",
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
