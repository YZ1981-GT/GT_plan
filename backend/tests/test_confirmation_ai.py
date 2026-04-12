"""
函证AI辅助服务单元测试
测试函证AI辅助核心功能
需求覆盖: 7.1-7.6
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import date, datetime
from uuid import uuid4

from app.services.confirmation_ai_service import ConfirmationAIService
from app.models.ai_models import (
    ConfirmationCheckType, ConfirmationRiskLevel, ConfirmationAICheck
)


class TestConfirmationAIService:
    """测试函证AI辅助服务"""

    @pytest.mark.asyncio
    async def test_verify_address(self):
        """测试地址核查"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        # Mock query result for ConfirmationList
        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "ABC客户有限公司"
        mock_confirmation.counterparty_address = "北京市朝阳区建国路88号"
        mock_confirmation.balance_or_amount = 1000000.00
        mock_confirmation.as_of_date = date(2024, 12, 31)
        mock_confirmation.confirmation_type = MagicMock()
        mock_confirmation.confirmation_type.value = "customer"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)

        # Mock async session execute
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        result = await service.verify_address(
            project_id=uuid4(),
            confirmation_id=mock_confirmation.id,
        )

        assert result is not None
        assert "match_score" in result
        assert "discrepancies" in result
        assert "check_result" in result

    @pytest.mark.asyncio
    async def test_verify_addresses_batch(self):
        """测试批量地址核查"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        # Mock query result for multiple Confirmations
        mock_confirmations = [
            MagicMock(
                id=uuid4(),
                counterparty_name="客户A",
                counterparty_address="北京市朝阳区",
                balance_or_amount=1000000.00,
                as_of_date=date(2024, 12, 31),
                confirmation_type=MagicMock(),
            ),
            MagicMock(
                id=uuid4(),
                counterparty_name="客户B",
                counterparty_address=None,  # 空地址
                balance_or_amount=500000.00,
                as_of_date=date(2024, 12, 31),
                confirmation_type=MagicMock(),
            ),
        ]

        # First execute returns confirmations list
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_confirmations)))

        # Subsequent executes for individual verification
        async def mock_execute_side_effect(*args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=mock_confirmations[0])
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute_side_effect)

        service = ConfirmationAIService(mock_db)

        results = await service.verify_addresses(
            project_id=uuid4(),
            confirmation_type="customer",
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_ocr_reply_scan(self):
        """测试回函OCR识别"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "ABC银行"
        mock_confirmation.balance_or_amount = 1000000.00
        mock_confirmation.as_of_date = date(2024, 12, 31)
        mock_confirmation.confirmation_type = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        # Mock AI service OCR
        with patch.object(service.ai, 'ocr_recognize', new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = {
                "text": "确认函\n截止2024年12月31日\n余额为1000000.00元\nXX银行XX支行业务专用章\n2024-01-20",
                "regions": []
            }

            with patch.object(service, '_extract_reply_fields', new_callable=AsyncMock) as mock_extract:
                mock_extract.return_value = {
                    "replying_entity": "ABC银行XX支行",
                    "confirmed_amount": 1000000.00,
                    "seal_detected": True,
                    "seal_name": "ABC银行XX支行业务专用章",
                    "reply_date": "2024-01-20",
                }

                result = await service.ocr_reply_scan(
                    project_id=uuid4(),
                    confirmation_id=mock_confirmation.id,
                    file_path="/test/reply.pdf",
                )

                assert result is not None
                assert "confirmed_amount" in result
                assert result["confirmed_amount"] == 1000000.00

    @pytest.mark.asyncio
    async def test_amount_comparison(self):
        """测试金额比对（通过analyze_mismatch_reason）"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "客户公司"
        mock_confirmation.balance_or_amount = 1000000.00
        mock_confirmation.as_of_date = date(2024, 12, 31)
        mock_confirmation.confirmation_type = MagicMock()
        mock_confirmation.confirmation_type.value = "customer"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        # Mock LLM analysis
        with patch.object(service, '_generate_mismatch_analysis', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "likely_reasons": [
                    "可能存在在途款项",
                    "双方入账时间差异",
                ],
                "suggested_reconciliation": "核对银行对账单",
            }

            result = await service.analyze_mismatch_reason(
                project_id=uuid4(),
                confirmation_id=mock_confirmation.id,
                original_amount=1000000.00,
                reply_amount=950000.00,
            )

            assert result is not None
            assert result["difference"] == 50000.00
            assert "likely_reasons" in result
            assert result["risk_level"] in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_check_seal(self):
        """测试印章检测"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "ABC银行XX支行"
        mock_confirmation.confirmation_type = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)
        mock_result.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        with patch.object(service, '_extract_reply_fields', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = {
                "seal_detected": True,
                "seal_name": "ABC银行XX支行业务专用章",
            }

            with patch.object(service.ai, 'ocr_recognize', new_callable=AsyncMock) as mock_ocr:
                mock_ocr.return_value = {"text": "银行业务专用章", "regions": []}

                result = await service.check_seal(
                    project_id=uuid4(),
                    confirmation_id=mock_confirmation.id,
                )

                assert result is not None
                assert "has_seal" in result
                assert "seal_text" in result
                assert "risk_level" in result

    @pytest.mark.asyncio
    async def test_missing_seal_alert(self):
        """测试印章缺失警报"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "客户公司"
        mock_confirmation.confirmation_type = MagicMock()
        mock_confirmation.confirmation_type.value = "customer"

        # Mock no OCR record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)
        mock_result.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        with patch.object(service, '_extract_reply_fields', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = {
                "seal_detected": False,
                "seal_name": None,
            }

            with patch.object(service.ai, 'ocr_recognize', new_callable=AsyncMock) as mock_ocr:
                mock_ocr.return_value = {"text": "无印章", "regions": []}

                result = await service.check_seal(
                    project_id=uuid4(),
                    confirmation_id=mock_confirmation.id,
                )

                assert result["has_seal"] == False
                assert result["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_discrepancy_analysis(self):
        """测试差异原因分析"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_confirmation = MagicMock()
        mock_confirmation.id = uuid4()
        mock_confirmation.counterparty_name = "客户公司"
        mock_confirmation.confirmation_type = MagicMock()
        mock_confirmation.confirmation_type.value = "customer"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_confirmation)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        with patch.object(service, '_generate_mismatch_analysis', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "likely_reasons": [
                    "客户已付款但未及时入账",
                    "存在在途款项",
                    "双方入账时间差异",
                ],
                "recommended_procedures": [
                    "检查银行对账单",
                    "函证期末银行余额",
                    "追踪款项后续情况",
                ],
            }

            result = await service.analyze_mismatch_reason(
                project_id=uuid4(),
                confirmation_id=mock_confirmation.id,
                original_amount=1000000.00,
                reply_amount=950000.00,
            )

            assert result is not None
            assert len(result["likely_reasons"]) > 0

    @pytest.mark.asyncio
    async def test_risk_level_classification_address(self):
        """测试地址风险等级分类"""
        mock_db = AsyncMock()

        service = ConfirmationAIService(mock_db)

        # 高风险：地址不匹配
        risk = service._classify_address_risk(
            match_score=30,
            discrepancies=["函证地址与注册地址不符"],
            confirmation_address="上海市浦东新区",
            registered_address="北京市朝阳区",
        )
        assert risk == "high"

        # 中风险：部分匹配
        risk = service._classify_address_risk(
            match_score=60,
            discrepancies=["未查询到工商登记地址"],
            confirmation_address="北京市朝阳区",
            registered_address=None,
        )
        assert risk == "medium"

        # 低风险：高度匹配
        risk = service._classify_address_risk(
            match_score=90,
            discrepancies=[],
            confirmation_address="北京市朝阳区建国路88号",
            registered_address="北京市朝阳区建国路88号",
        )
        assert risk == "low"

    @pytest.mark.asyncio
    async def test_check_type_enum(self):
        """测试检查类型枚举"""
        assert ConfirmationCheckType.address_verify.value == "address_verify"
        assert ConfirmationCheckType.reply_ocr.value == "reply_ocr"
        assert ConfirmationCheckType.amount_compare.value == "amount_compare"
        assert ConfirmationCheckType.seal_check.value == "seal_check"

    @pytest.mark.asyncio
    async def test_get_ai_checks(self):
        """测试获取AI检查结果列表"""
        mock_db = AsyncMock()

        mock_check = MagicMock()
        mock_check.id = uuid4()
        mock_check.confirmation_list_id = uuid4()
        mock_check.check_type = ConfirmationCheckType.address_verify
        mock_check.check_result = {"match_score": 85}
        mock_check.risk_level = ConfirmationRiskLevel.low
        mock_check.human_confirmed = False
        mock_check.confirmed_by = None
        mock_check.confirmed_at = None
        mock_check.created_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_check])))
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        results = await service.get_ai_checks(
            project_id=uuid4(),
        )

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["check_type"] == "address_verify"

    @pytest.mark.asyncio
    async def test_confirm_ai_check(self):
        """测试确认AI检查结果"""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_check = MagicMock()
        mock_check.id = uuid4()
        mock_check.check_result = {"match_score": 85}
        mock_check.human_confirmed = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_check)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ConfirmationAIService(mock_db)

        result = await service.confirm_ai_check(
            check_id=mock_check.id,
            user_id=uuid4(),
            action="accept",
            notes="确认无误",
        )

        assert result["human_confirmed"] == True
        assert mock_check.human_confirmed == True

    @pytest.mark.asyncio
    async def test_text_similarity(self):
        """测试文本相似度计算"""
        mock_db = AsyncMock()
        service = ConfirmationAIService(mock_db)

        # 相同文本
        sim = service._calculate_text_similarity(
            "北京市朝阳区建国路88号",
            "北京市朝阳区建国路88号",
        )
        assert sim == 1.0

        # 部分相似
        sim = service._calculate_text_similarity(
            "北京市朝阳区建国路88号",
            "北京市朝阳区建国路99号",
        )
        assert 0.5 < sim < 1.0

        # 完全不同
        sim = service._calculate_text_similarity(
            "北京市朝阳区",
            "上海市浦东新区",
        )
        assert sim < 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
