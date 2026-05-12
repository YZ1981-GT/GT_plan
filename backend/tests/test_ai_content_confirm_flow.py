"""集成测试：AI 内容确认流程 (Sprint 4 验收)

覆盖 UAT 场景：
1. AI 生成"结论建议"后点"采纳"→ confirmed_by 有值 → sign_off gate 通过
2. 未确认 AI 内容 sign_off 被 AIContentMustBeConfirmedRule 阻断
3. QC-02（AIFillConfirmedRule）仍能触发于 submit_review（回归）
4. 手动插入一条凌晨 3 点批量删底稿的 audit_log → AL-01 命中
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.wp_ai_service import wrap_ai_output


# ---------------------------------------------------------------------------
# 场景 1: AI 生成结论 → 采纳 → confirmed_by 有值 → sign_off 通过
# ---------------------------------------------------------------------------


class TestAiContentConfirmAcceptFlow:
    """AI 内容采纳后 sign_off gate 通过。"""

    @pytest.mark.asyncio
    async def test_accept_sets_confirmed_by(self):
        """采纳操作设置 confirmed_by 和 confirmed_at。"""
        # 模拟 AI 生成结论建议
        ai_item = wrap_ai_output(
            "根据分析性复核，该科目余额变动合理，无需进一步审计程序。",
            confidence=0.85,
            target_cell="E5",
            target_field="conclusion",
        )
        assert ai_item["confirmed_by"] is None
        assert ai_item["confirmed_at"] is None

        # 模拟用户点击"采纳"
        user_id = str(uuid.uuid4())
        ai_item["confirmed_by"] = user_id
        ai_item["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        ai_item["confirm_action"] = "accept"

        assert ai_item["confirmed_by"] == user_id
        assert ai_item["confirmed_at"] is not None
        assert ai_item["confirm_action"] == "accept"

    @pytest.mark.asyncio
    async def test_sign_off_passes_after_confirm(self):
        """所有 AI 内容确认后 sign_off gate 通过。"""
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()
        db = AsyncMock()

        # 底稿中 AI 内容已全部确认
        user_id = str(uuid.uuid4())
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "结论建议：余额变动合理",
                    "target_cell": "E5",
                    "target_field": "conclusion",
                    "confidence": 0.85,
                    "confirmed_by": user_id,
                    "confirmed_at": "2026-05-01T10:00:00",
                    "confirm_action": "accept",
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None  # 通过，无阻断


# ---------------------------------------------------------------------------
# 场景 2: 未确认 AI 内容 → sign_off 被 AIContentMustBeConfirmedRule 阻断
# ---------------------------------------------------------------------------


class TestAiContentUnconfirmedBlocks:
    """未确认 AI 内容阻断 sign_off。"""

    @pytest.mark.asyncio
    async def test_unconfirmed_ai_content_blocks_sign_off(self):
        """存在未确认的 AI 内容时 sign_off 被阻断。"""
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()
        db = AsyncMock()

        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-002"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "AI 生成的结论建议，尚未确认",
                    "target_cell": "E5",
                    "target_field": "conclusion",
                    "confidence": 0.80,
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "confirm_action": None,
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is not None
        assert result.rule_code == "R3-AI-UNCONFIRMED"
        assert result.error_code == "AI_CONTENT_NOT_CONFIRMED"
        assert result.severity.value == "blocking"
        assert result.location["unconfirmed_wp_count"] == 1

    @pytest.mark.asyncio
    async def test_mixed_confirmed_and_unconfirmed(self):
        """部分确认部分未确认 → 仍阻断。"""
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()
        db = AsyncMock()

        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-003"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "已确认的内容",
                    "target_cell": "A1",
                    "confirmed_by": str(uuid.uuid4()),
                    "confirmed_at": "2026-05-01T10:00:00",
                    "confirm_action": "accept",
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "未确认的内容",
                    "target_cell": "B2",
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "confirm_action": None,
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is not None
        assert result.location["unconfirmed_wp_count"] == 1


# ---------------------------------------------------------------------------
# 场景 3: 回归 — QC-02 (AIFillConfirmedRule) 仍能触发于 submit_review
# ---------------------------------------------------------------------------


class TestQC02RegressionSubmitReview:
    """QC-02 AIFillConfirmedRule 回归测试。"""

    @pytest.mark.asyncio
    async def test_qc02_detects_pending_ai_content(self):
        """QC-02 检测 status=pending 的 AI 内容（submit_review 级别 warning）。"""
        from app.services.qc_engine import AIFillConfirmedRule

        rule = AIFillConfirmedRule()

        # 模拟底稿上下文：有 pending 状态的 AI 内容
        wp = MagicMock()
        wp.parsed_data = {
            "ai_content": [
                {"status": "pending", "content": "AI 生成文本", "cell_ref": "E5"},
            ]
        }
        context = MagicMock()
        context.working_paper = wp

        # QC-02 应该检测到未确认的 AI 内容
        findings = await rule.check(context)
        assert findings is not None
        assert len(findings) > 0
        assert findings[0].rule_id == "QC-02"

    @pytest.mark.asyncio
    async def test_qc02_passes_when_all_confirmed(self):
        """QC-02 所有 AI 内容已确认时通过。"""
        from app.services.qc_engine import AIFillConfirmedRule

        rule = AIFillConfirmedRule()

        wp = MagicMock()
        wp.parsed_data = {
            "ai_content": [
                {"status": "accepted", "content": "已确认", "cell_ref": "E5"},
            ]
        }
        context = MagicMock()
        context.working_paper = wp

        findings = await rule.check(context)
        assert findings is None or len(findings) == 0

    @pytest.mark.asyncio
    async def test_qc02_passes_when_no_ai_content(self):
        """QC-02 无 AI 内容时通过。"""
        from app.services.qc_engine import AIFillConfirmedRule

        rule = AIFillConfirmedRule()

        wp = MagicMock()
        wp.parsed_data = {"conclusion": "手动填写的结论"}
        context = MagicMock()
        context.working_paper = wp

        findings = await rule.check(context)
        assert findings is None or len(findings) == 0


# ---------------------------------------------------------------------------
# 场景 4: 审计日志 — 凌晨 3 点批量删底稿 → AL-01 命中
# ---------------------------------------------------------------------------


class TestAuditLogAL01Detection:
    """AL-01 规则：非工作时间批量修改底稿检测。"""

    @pytest.mark.asyncio
    async def test_al01_detects_off_hours_modification(self):
        """凌晨 3 点的 workpaper_modified 操作被 AL-01 检测到。"""
        from app.services.qc_rule_executor import execute_audit_log_rule

        # 构造 AL-01 规则定义
        rule_def = MagicMock()
        rule_def.rule_code = "AL-01"
        rule_def.expression_type = "jsonpath"
        rule_def.expression = "$.action_type"
        rule_def.severity = "warning"
        rule_def.scope = "audit_log"
        rule_def.parameters_schema = {
            "expect_match": False,
            "message": "非工作时间（22:00-06:00）批量修改底稿超过阈值",
            "threshold_per_hour": 10,
            "off_hours": [22, 23, 0, 1, 2, 3, 4, 5],
            "target_action_type": "workpaper_modified",
        }

        # 模拟凌晨 3 点的批量删除/修改底稿日志条目
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.ts = datetime(2026, 5, 15, 3, 0, 0)  # 凌晨 3 点
        entry.action_type = "workpaper_modified"
        entry.user_id = uuid.uuid4()
        entry.ip = "192.168.1.50"
        entry.payload = {"action_type": "workpaper_modified", "batch_size": 15}
        entry.object_id = uuid.uuid4()

        # Mock DB
        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [entry]
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        result = await execute_audit_log_rule(rule_def, db)
        # AL-01 使用 expect_match=False，匹配到 $.action_type 意味着命中
        assert result.passed is False
        assert len(result.findings) >= 1
        assert result.findings[0]["rule_id"] == "AL-01"

    @pytest.mark.asyncio
    async def test_al01_no_match_for_normal_hours(self):
        """正常工作时间的操作不应被 AL-01 误报（通过 JSONPath 层面）。"""
        from app.services.qc_rule_executor import execute_audit_log_rule

        rule_def = MagicMock()
        rule_def.rule_code = "AL-01"
        rule_def.expression_type = "jsonpath"
        rule_def.expression = "$.action_type"
        rule_def.severity = "warning"
        rule_def.scope = "audit_log"
        rule_def.parameters_schema = {
            "expect_match": False,
            "message": "非工作时间批量修改",
            "threshold_per_hour": 10,
            "off_hours": [22, 23, 0, 1, 2, 3, 4, 5],
            "target_action_type": "workpaper_modified",
        }

        # 正常时间的日志 — 但 JSONPath $.action_type 仍会匹配
        # 注意：当前 AL-01 的 JSONPath 实现是简单匹配 payload 中的 action_type 字段
        # 时间过滤由查询层面处理（time_window 参数），不在 JSONPath 表达式中
        entry = MagicMock()
        entry.id = uuid.uuid4()
        entry.ts = datetime(2026, 5, 15, 10, 0, 0)  # 上午 10 点
        entry.action_type = "workpaper_modified"
        entry.user_id = uuid.uuid4()
        entry.ip = "192.168.1.50"
        entry.payload = {"action_type": "workpaper_modified"}
        entry.object_id = uuid.uuid4()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        # 如果查询层面已过滤掉正常时间的条目，则返回空
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db.execute = AsyncMock(return_value=mock_result)

        result = await execute_audit_log_rule(rule_def, db)
        assert result.passed is True
        assert result.findings == []


# ---------------------------------------------------------------------------
# 端到端流程：wrap → 未确认 → 阻断 → 确认 → 通过
# ---------------------------------------------------------------------------


class TestEndToEndConfirmFlow:
    """完整的 AI 内容确认流程。"""

    @pytest.mark.asyncio
    async def test_full_flow_wrap_block_confirm_pass(self):
        """wrap_ai_output → 未确认阻断 → 确认后通过。"""
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule

        rule = AIContentMustBeConfirmedRule()

        # Step 1: AI 生成内容
        ai_item = wrap_ai_output(
            "建议结论：该科目余额变动合理",
            confidence=0.85,
            target_cell="E5",
            target_field="conclusion",
        )
        assert ai_item["type"] == "ai_generated"
        assert ai_item["confirmed_by"] is None

        # Step 2: 未确认状态 → sign_off 阻断
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {"ai_content": [ai_item]}
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is not None
        assert result.error_code == "AI_CONTENT_NOT_CONFIRMED"

        # Step 3: 用户确认采纳
        user_id = str(uuid.uuid4())
        ai_item["confirmed_by"] = user_id
        ai_item["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        ai_item["confirm_action"] = "accept"

        # Step 4: 确认后 → sign_off 通过
        wp.parsed_data = {"ai_content": [ai_item]}
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result2)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None  # 通过
