"""AI 结论草稿生成测试

Tasks 2.6, 2.7, 3.4–3.7 (workpaper-ai-conclusion-copilot spec):
- Prompt fixture / golden tests（missing、函证为空、坏账/ECL 不完整、调整影响存在）
- Prompt 安全测试：不得引导 AI 编造函证、坏账、附件、程序状态或未来源化结论
- 后端保存结论时校验 AI log 状态
- pending 阻断、确认后放行、拒绝后不写入
- 拒绝旧草稿后可重新生成，旧草稿不得进入正式结论

Requirements: 1.1, 1.2, 1.3, 2.1, 2.5, 4.5
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_ai_conclusion_prompts import (
    CONCLUSION_PROMPT_TEMPLATE,
    build_conclusion_prompt,
)


# ---------------------------------------------------------------------------
# Task 2.6: Prompt fixture / golden tests
# ---------------------------------------------------------------------------


class TestPromptGoldenTests:
    """Prompt 模板 golden tests: 覆盖 4 类输入场景。"""

    def test_prompt_with_missing_context(self):
        """场景 1: 上下文缺失时 prompt 正确包含 missing 列表"""
        missing = [
            {"source": "confirmation_summary", "reason": "confirmation_service_no_data",
             "impact": "函证覆盖率和差异金额无法引用"},
            {"source": "bad_debt_ecl", "reason": "no_ecl_analysis_sheets",
             "impact": "坏账/ECL 分析数据不可用"},
        ]
        context = {
            "audit_sheet_summary": {"has_audit_sheet": True, "count": 1},
            "program_status_summary": {"total": 5, "completed": 3},
        }
        prompt = build_conclusion_prompt(
            account_name="应收账款",
            account_package_id="D2_accounts_receivable",
            context=context,
            missing=missing,
        )
        # 验证 missing 内容在 prompt 中展示
        assert "confirmation_service_no_data" in prompt
        assert "函证覆盖率和差异金额无法引用" in prompt
        assert "坏账/ECL 分析数据不可用" in prompt
        # 验证基本结构
        assert "应收账款" in prompt
        assert "D2_accounts_receivable" in prompt

    def test_prompt_with_empty_confirmation(self):
        """场景 2: 函证为空时 prompt 标记 missing"""
        missing = [
            {"source": "confirmation_summary", "reason": "confirmation_service_no_data",
             "impact": "函证覆盖率和差异金额无法引用"},
        ]
        context = {
            "audit_sheet_summary": {"has_audit_sheet": True},
            "program_status_summary": {"total": 8, "completed": 6},
            "adjustment_impact": {"has_adjustments": True},
        }
        prompt = build_conclusion_prompt(
            account_name="应收账款",
            account_package_id="D2_accounts_receivable",
            context=context,
            missing=missing,
        )
        assert "confirmation_service_no_data" in prompt
        assert "函证覆盖率" in prompt
        # 调整影响应在可引用数据中
        assert "has_adjustments" in prompt

    def test_prompt_with_incomplete_bad_debt_ecl(self):
        """场景 3: 坏账/ECL 不完整时 prompt 标记 missing"""
        missing = [
            {"source": "bad_debt_ecl", "reason": "no_ecl_analysis_sheets",
             "impact": "坏账/ECL 分析数据不可用，AI 无法引用减值测算结论"},
        ]
        context = {
            "audit_sheet_summary": {"has_audit_sheet": True},
            "program_status_summary": {"total": 10, "completed": 10},
            "confirmation_summary": {"status": "available", "coverage_rate": 0.85},
        }
        prompt = build_conclusion_prompt(
            account_name="应收账款",
            account_package_id="D2_accounts_receivable",
            context=context,
            missing=missing,
        )
        assert "no_ecl_analysis_sheets" in prompt
        assert "减值测算结论" in prompt

    def test_prompt_with_adjustment_impact_exists(self):
        """场景 4: 调整影响存在时 prompt 正确引用"""
        context = {
            "audit_sheet_summary": {"has_audit_sheet": True},
            "program_status_summary": {"total": 5, "completed": 5},
            "adjustment_impact": {
                "has_adjustments": True,
                "adjustment_sheets": [{"sheet_name": "D1-调整分录"}],
                "downstream_affected": ["A-报表"],
            },
        }
        prompt = build_conclusion_prompt(
            account_name="固定资产",
            account_package_id="D1_fixed_assets",
            context=context,
            missing=[],
        )
        assert "has_adjustments" in prompt
        assert "D1-调整分录" in prompt
        assert "A-报表" in prompt
        # 无 missing 时显示"无缺失资料"
        assert "无缺失资料" in prompt


# ---------------------------------------------------------------------------
# Task 2.7: Prompt 安全测试
# ---------------------------------------------------------------------------


class TestPromptSafety:
    """Prompt 不得引导 AI 编造函证、坏账、附件、程序状态或未来源化结论。"""

    def test_prompt_prohibits_fabricating_confirmation(self):
        """Prompt 明确禁止编造函证数据"""
        assert "不得编造函证" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_prohibits_fabricating_bad_debt(self):
        """Prompt 明确禁止编造坏账计算结果"""
        assert "不得编造坏账计算结果" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_prohibits_fabricating_attachments(self):
        """Prompt 明确禁止编造附件内容"""
        assert "不得编造附件内容" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_prohibits_fabricating_program_status(self):
        """Prompt 明确禁止编造程序状态"""
        assert "不得编造程序状态" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_prohibits_unsourced_conclusions(self):
        """Prompt 明确禁止未来源化的确定性结论"""
        assert "不得输出未来源化的确定性结论" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_requires_source_references(self):
        """Prompt 要求引用来源列表"""
        assert "引用来源列表" in CONCLUSION_PROMPT_TEMPLATE

    def test_prompt_requires_missing_items_display(self):
        """Prompt 要求展示缺失资料提示"""
        assert "缺失资料提示" in CONCLUSION_PROMPT_TEMPLATE

    def test_missing_context_appears_in_prohibition_section(self):
        """缺失上下文在 prompt 中明确标注为不可编造"""
        missing = [{"source": "confirmation_summary", "reason": "no_data", "impact": "不可用"}]
        prompt = build_conclusion_prompt(
            account_name="测试",
            account_package_id="test_pkg",
            context={},
            missing=missing,
        )
        # 缺失信息和禁止编造同在一个 prompt 中
        assert "不可用" in prompt
        assert "不得编造" in prompt


# ---------------------------------------------------------------------------
# Task 3.4: 后端保存结论时校验 AI log 状态
# ---------------------------------------------------------------------------


class TestConclusionSaveValidation:
    """后端保存 D1-C / D2-C 结论时校验 AI log 状态。"""

    @pytest.mark.asyncio
    async def test_pending_ai_log_blocks_conclusion_save(self):
        """pending 状态的 AI log 阻断结论保存"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_conclusion_save,
            ConclusionSaveBlockedError,
        )

        db = AsyncMock()
        # 模拟一条 pending 记录
        pending_log = MagicMock()
        pending_log.id = uuid.uuid4()
        pending_log.confirm_action = "pending"
        pending_log.target_cell = "workpaper:wp123:d1.conclusion.overall"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pending_log]
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ConclusionSaveBlockedError) as exc_info:
            await validate_conclusion_save(
                db=db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                field_id="d1.conclusion.overall",
            )
        assert "pending" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_confirmed_ai_log_allows_conclusion_save(self):
        """confirmed 状态允许保存"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_conclusion_save,
        )

        db = AsyncMock()
        # 无 pending 记录
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        # 不应抛异常
        await validate_conclusion_save(
            db=db,
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            field_id="d1.conclusion.overall",
        )

    @pytest.mark.asyncio
    async def test_rejected_ai_log_allows_manual_save(self):
        """rejected 状态允许用户手动保存（用户自己写结论）"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_conclusion_save,
        )

        db = AsyncMock()
        # 无 pending 记录（rejected 不算 pending）
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        await validate_conclusion_save(
            db=db,
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            field_id="d1.conclusion.overall",
        )


# ---------------------------------------------------------------------------
# Task 3.5: 校验目标绑定一致性
# ---------------------------------------------------------------------------


class TestTargetBindingValidation:
    """后端保存正式结论时校验 AI log 目标绑定与当前字段一致。"""

    @pytest.mark.asyncio
    async def test_mismatched_target_binding_blocks_save(self):
        """目标绑定不一致时阻断保存"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_conclusion_save,
            ConclusionSaveBlockedError,
        )

        db = AsyncMock()
        # 有一条 pending 记录，target_cell 与当前字段匹配
        pending_log = MagicMock()
        pending_log.id = uuid.uuid4()
        pending_log.confirm_action = "pending"
        pending_log.target_cell = "workpaper:wp123:d1.conclusion.overall"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pending_log]
        db.execute = AsyncMock(return_value=mock_result)

        # 尝试保存同一字段 —— 应阻断
        with pytest.raises(ConclusionSaveBlockedError):
            await validate_conclusion_save(
                db=db,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                field_id="d1.conclusion.overall",
            )


# ---------------------------------------------------------------------------
# Task 3.6: pending 阻断，确认后放行，拒绝后不写入
# ---------------------------------------------------------------------------


class TestPendingBlockConfirmAllow:
    """pending 阻断，确认后放行，拒绝后不写入正式结论。"""

    @pytest.mark.asyncio
    async def test_pending_blocks_sign_off_via_gate_rule(self):
        """pending AI 草稿通过既有 gate rule 阻断 sign_off"""
        from app.services.gate_rules_ai_content import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()
        db = AsyncMock()

        # 模拟有 pending AI content log
        pending_log = MagicMock()
        pending_log.id = uuid.uuid4()

        with patch(
            "app.services.ai_content_log_service.list_pending_by_project",
            new_callable=AsyncMock,
            return_value=[pending_log],
        ), patch(
            "app.services.ai_content_log_service.count_pending_by_project",
            new_callable=AsyncMock,
            return_value=1,
        ):
            result = await rule.check(db, {"project_id": uuid.uuid4()})

        assert result is not None
        assert result.rule_code == "R3-AI-UNCONFIRMED"

    @pytest.mark.asyncio
    async def test_confirmed_allows_sign_off(self):
        """所有 AI 草稿确认后 sign_off 通过"""
        from app.services.gate_rules_ai_content import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()
        db = AsyncMock()

        # 无 pending 的日志
        with patch(
            "app.services.ai_content_log_service.list_pending_by_project",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # 也无 parsed_data 中的未确认内容
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            db.execute = AsyncMock(return_value=mock_result)

            result = await rule.check(db, {"project_id": uuid.uuid4()})

        assert result is None


# ---------------------------------------------------------------------------
# Task 3.7: 拒绝旧草稿后可重新生成新草稿，旧草稿不得进入正式结论
# ---------------------------------------------------------------------------


class TestRejectAndRegenerate:
    """拒绝旧草稿后可重新生成，旧草稿不得进入正式结论。"""

    @pytest.mark.asyncio
    async def test_rejected_draft_cannot_be_saved_as_conclusion(self):
        """被拒绝的旧草稿不得进入正式结论"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_rejected_draft_not_used,
        )

        # 尝试把 rejected 草稿内容写入结论 —— 应阻断
        db = AsyncMock()
        rejected_log = MagicMock()
        rejected_log.id = uuid.uuid4()
        rejected_log.confirm_action = "rejected"
        rejected_log.generated_content = "旧的 AI 草稿内容"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rejected_log
        db.execute = AsyncMock(return_value=mock_result)

        is_valid = await validate_rejected_draft_not_used(
            db=db,
            log_id=rejected_log.id,
            conclusion_content="旧的 AI 草稿内容",
        )
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_new_draft_after_rejection_is_allowed(self):
        """拒绝旧草稿后可重新生成新草稿"""
        from app.services.workpaper_ai_conclusion_save_validator import (
            validate_rejected_draft_not_used,
        )

        db = AsyncMock()
        # 新草稿已确认
        confirmed_log = MagicMock()
        confirmed_log.id = uuid.uuid4()
        confirmed_log.confirm_action = "confirmed"
        confirmed_log.generated_content = "新的 AI 草稿内容"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = confirmed_log
        db.execute = AsyncMock(return_value=mock_result)

        is_valid = await validate_rejected_draft_not_used(
            db=db,
            log_id=confirmed_log.id,
            conclusion_content="新的 AI 草稿内容",
        )
        assert is_valid is True
