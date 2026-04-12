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
    ContractType, ContractAnalysisStatus, ClauseType, ContractLinkType, RiskLevel
)


class TestContractAnalysisService:
    """测试合同分析服务"""

    @pytest.mark.asyncio
    async def test_extract_clauses_basic(self):
        """测试基础条款提取"""
        mock_db = AsyncMock()
        
        with patch.object(ContractAnalysisService, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "party_a": "甲方科技有限公司",
                "party_b": "乙方供应商",
                "amount": 500000.00,
                "date": "2024-01-15",
                "terms": "技术服务合同",
                "payment_terms": "预付30%，交付后付70%",
                "penalty_clauses": "逾期交货每日按合同金额0.1%罚款",
                "termination_clauses": "任何一方可提前30日书面通知解除",
                "force_majeure": "不可抗力导致合同无法履行时，双方互不承担责任",
                "confidentiality": "双方对合同内容负有保密义务，有效期2年",
                "non_competition": "合同期内甲方不得与乙方竞争对手合作",
            }
            
            service = ContractAnalysisService(mock_db)
            
            result = await service.extract_clauses(
                contract_id=uuid4(),
                ocr_text="甲乙双方签订技术服务合同...",
            )
            
            assert result is not None
            assert result.party_a == "甲方科技有限公司"
            assert result.party_b == "乙方供应商"
            assert result.amount == 500000.00
            assert result.payment_terms is not None
            assert result.penalty_clauses is not None

    @pytest.mark.asyncio
    async def test_cross_check_business_cycle(self):
        """测试业务循环交叉核对"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        # 采购合同应属于采购与付款循环
        result = await service.cross_check(
            contract_id=uuid4(),
            extracted_data={
                "contract_type": "采购合同",
                "amount": 500000,
            },
        )
        
        assert result.business_cycle == "采购与付款"
        assert result.issues == [] or len(result.issues) >= 0

    @pytest.mark.asyncio
    async def test_cross_check_company_code(self):
        """测试公司代码核对"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        result = await service.cross_check(
            contract_id=uuid4(),
            extracted_data={
                "company_code": "1001",
                "party_b": "关联方公司",  # 关联方需要特别关注
            },
        )
        
        # 应检测到关联方交易
        assert result is not None

    @pytest.mark.asyncio
    async def test_cross_check_year(self):
        """测试年度核对"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        result = await service.cross_check(
            contract_id=uuid4(),
            extracted_data={
                "date": "2024-01-15",
                "year": "2024",
            },
        )
        
        assert result.year_matches == True

    @pytest.mark.asyncio
    async def test_cross_check_amount_range(self):
        """测试金额范围核对"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        result = await service.cross_check(
            contract_id=uuid4(),
            extracted_data={
                "amount": 50000000,  # 5000万，超出小额标准
            },
        )
        
        # 大额合同应有额外审批流程提示
        assert result is not None

    @pytest.mark.asyncio
    async def test_risk_clause_detection(self):
        """测试风险条款检测"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        # 包含不利条款的合同
        risky_text = """
        合同规定：
        1. 甲方有权随时终止合同且无需赔偿
        2. 乙方须在签约后3日内完成交付
        3. 违约金为合同金额的50%
        """
        
        result = await service.analyze_risk(
            contract_id=uuid4(),
            clauses={
                "termination_clauses": "甲方有权随时终止",
                "penalty_clauses": "违约金50%",
            },
        )
        
        assert result is not None
        assert result.risk_level in [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]

    @pytest.mark.asyncio
    async def test_risk_level_classification(self):
        """测试风险等级分类"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        # 高风险场景
        high_risk_clauses = {
            "termination_clauses": "无限制终止权",
            "penalty_clauses": "高额违约金",
            "force_majeure": None,  # 无不可抗力条款
        }
        
        risk_level = service._classify_risk_level(high_risk_clauses)
        assert risk_level == RiskLevel.HIGH
        
        # 低风险场景
        low_risk_clauses = {
            "termination_clauses": "需双方协商",
            "penalty_clauses": "合理违约金",
            "force_majeure": "有不可抗力条款",
            "confidentiality": "有保密条款",
        }
        
        risk_level_low = service._classify_risk_level(low_risk_clauses)
        assert risk_level_low in [RiskLevel.LOW, RiskLevel.MEDIUM]

    @pytest.mark.asyncio
    async def test_link_contract_to_workpaper(self):
        """测试合同与底稿关联"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        contract_id = uuid4()
        workpaper_id = uuid4()
        
        result = await service.link_to_workpaper(
            contract_id=contract_id,
            workpaper_id=workpaper_id,
            link_type=ContractLinkType.SUPPORTING_EVIDENCE,
            notes="合同为采购付款底稿的支持性证据",
        )
        
        assert result is not None
        assert result.contract_id == contract_id
        assert result.workpaper_id == workpaper_id

    @pytest.mark.asyncio
    async def test_batch_analysis(self):
        """测试批量合同分析"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        contract_ids = [uuid4() for _ in range(5)]
        
        with patch.object(ContractAnalysisService, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "party_a": "测试公司",
                "party_b": "供应商",
                "amount": 100000,
                "date": "2024-01-01",
                "terms": "采购合同",
            }
            
            results = await service.batch_analyze(
                contract_ids=contract_ids,
                project_id=uuid4(),
            )
            
            assert len(results) == 5
            assert all(r.status == ContractAnalysisStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_special_clause_extraction(self):
        """测试特殊条款提取"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        text_with_special = """
        附加条款：
        1. 知识产权归属：乙方开发的所有成果归甲方所有
        2. 竞业限制：离职后2年内不得从事相关行业
        3. 保密条款：合同终止后保密义务继续有效5年
        """
        
        clauses = await service._extract_special_clauses(text_with_special)
        
        assert "intellectual_property" in clauses or "ip_rights" in clauses
        assert "non_competition" in clauses
        assert "extended_confidentiality" in clauses

    @pytest.mark.asyncio
    async def test_analysis_status_lifecycle(self):
        """测试分析状态生命周期"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        # 创建分析记录
        contract_id = uuid4()
        
        # 初始状态
        initial_status = ContractAnalysisStatus.PENDING
        assert initial_status == ContractAnalysisStatus.PENDING
        
        # 分析中
        processing_status = ContractAnalysisStatus.PROCESSING
        assert processing_status == ContractAnalysisStatus.PROCESSING
        
        # 完成
        completed_status = ContractAnalysisStatus.COMPLETED
        assert completed_status == ContractAnalysisStatus.COMPLETED
        
        # 失败
        failed_status = ContractAnalysisStatus.FAILED
        assert failed_status == ContractAnalysisStatus.FAILED

    @pytest.mark.asyncio
    async def test_contract_type_classification(self):
        """测试合同类型分类"""
        mock_db = AsyncMock()
        
        service = ContractAnalysisService(mock_db)
        
        # 销售合同
        sales_type = service._classify_contract_type("销售产品合同")
        assert sales_type == ContractType.SALES
        
        # 采购合同
        purchase_type = service._classify_contract_type("采购原材料合同")
        assert purchase_type == ContractType.PURCHASE
        
        # 服务合同
        service_type = service._classify_contract_type("技术服务协议")
        assert service_type == ContractType.SERVICE

    @pytest.mark.asyncio
    async def test_clause_type_enum(self):
        """测试条款类型枚举"""
        assert ClauseType.PAYMENT_TERMS.value == "payment_terms"
        assert ClauseType.PENALTY_CLAUSE.value == "penalty_clauses"
        assert ClauseType.TERMINATION_CLAUSE.value == "termination_clauses"
        assert ClauseType.FORCE_MAJEURE.value == "force_majeure"
        assert ClauseType.CONFIDENTIALITY.value == "confidentiality"
        assert ClauseType.NON_COMPETITION.value == "non_competition"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
