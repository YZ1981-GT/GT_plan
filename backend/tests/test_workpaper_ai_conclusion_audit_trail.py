"""AI 结论审计留痕测试

Task 5 (workpaper-ai-conclusion-copilot spec):
- 5.1 记录 prompt、模型、上下文摘要
- 5.2 记录 AI 原文、用户修订文、确认/拒绝人
- 5.3 拒绝时要求原因
- 5.4 来源摘要可跳转到字段来源或工作包卡片
- 5.5 AI content log 治理面板可按目标绑定跳转回 D1-C / D2-C
- 5.6 AI content log 查询可按 account_package_id、wp_id、field_id 过滤并跳转

Requirements: 5.1, 3.4
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workpaper_ai_conclusion_audit_trail import (
    record_draft_generation_audit,
    record_confirm_audit,
    record_revise_audit,
    record_reject_audit,
    build_source_jump_links,
    build_governance_jump_link,
    query_ai_content_logs_by_binding,
)


# ---------------------------------------------------------------------------
# 5.1: 记录 prompt、模型、上下文摘要
# ---------------------------------------------------------------------------


class TestDraftGenerationAudit:
    """Task 5.1: 草稿生成审计轨迹。"""

    @pytest.mark.asyncio
    async def test_record_draft_generation_audit(self):
        """记录 prompt 长度、模型和上下文摘要"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        log_id = uuid.uuid4()

        with patch("app.services.workpaper_ai_conclusion_audit_trail.append_audit_log") as mock_append:
            mock_append.return_value = None
            await record_draft_generation_audit(
                db=db,
                project_id=project_id,
                user_id=user_id,
                log_id=log_id,
                prompt_text="这是一个测试 prompt 文本",
                model="qwen3.5-27b",
                context_summary={"sources": [{"type": "audit_sheet", "label": "审定表"}]},
                target_binding={
                    "account_package_id": "D1_fixed_assets",
                    "wp_id": str(uuid.uuid4()),
                    "sheet_type": "conclusion",
                    "field_id": "d1.conclusion.overall",
                },
            )

            mock_append.assert_called_once()
            call_args = mock_append.call_args[0]
            details = call_args[1]["details"]
            assert details["event_type"] == "ai_conclusion_draft_generated"
            assert details["model"] == "qwen3.5-27b"
            assert details["prompt_length"] > 0
            assert "context_summary" in details
            assert "target_binding" in details


# ---------------------------------------------------------------------------
# 5.2: 记录 AI 原文、用户修订文、确认/拒绝人
# ---------------------------------------------------------------------------


class TestConfirmReviseAudit:
    """Task 5.2: 确认和修订审计轨迹。"""

    @pytest.mark.asyncio
    async def test_record_confirm_audit(self):
        """记录确认人"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        log_id = uuid.uuid4()

        with patch("app.services.workpaper_ai_conclusion_audit_trail.append_audit_log") as mock_append:
            mock_append.return_value = None
            await record_confirm_audit(
                db=db,
                project_id=project_id,
                user_id=user_id,
                log_id=log_id,
            )

            mock_append.assert_called_once()
            details = mock_append.call_args[0][1]["details"]
            assert details["event_type"] == "ai_conclusion_confirmed"
            assert details["confirmed_by"] == str(user_id)

    @pytest.mark.asyncio
    async def test_record_revise_audit(self):
        """记录 AI 原文长度和修订文长度"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        log_id = uuid.uuid4()

        with patch("app.services.workpaper_ai_conclusion_audit_trail.append_audit_log") as mock_append:
            mock_append.return_value = None
            await record_revise_audit(
                db=db,
                project_id=project_id,
                user_id=user_id,
                log_id=log_id,
                original_content="AI 生成的原始结论内容",
                revised_content="用户修订后的结论内容，增加了补充说明",
            )

            mock_append.assert_called_once()
            details = mock_append.call_args[0][1]["details"]
            assert details["event_type"] == "ai_conclusion_revised"
            assert details["revised_by"] == str(user_id)
            assert details["original_content_length"] > 0
            assert details["revised_content_length"] > 0


# ---------------------------------------------------------------------------
# 5.3: 拒绝时要求原因
# ---------------------------------------------------------------------------


class TestRejectAudit:
    """Task 5.3: 拒绝时要求填写原因。"""

    @pytest.mark.asyncio
    async def test_record_reject_audit_with_reason(self):
        """拒绝时记录原因"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        log_id = uuid.uuid4()

        with patch("app.services.workpaper_ai_conclusion_audit_trail.append_audit_log") as mock_append:
            mock_append.return_value = None
            await record_reject_audit(
                db=db,
                project_id=project_id,
                user_id=user_id,
                log_id=log_id,
                reject_reason="AI 草稿引用了不准确的函证数据",
            )

            mock_append.assert_called_once()
            details = mock_append.call_args[0][1]["details"]
            assert details["event_type"] == "ai_conclusion_rejected"
            assert details["rejected_by"] == str(user_id)
            assert details["reject_reason"] == "AI 草稿引用了不准确的函证数据"

    @pytest.mark.asyncio
    async def test_reject_requires_non_empty_reason(self):
        """拒绝原因不能为空"""
        db = AsyncMock()
        with pytest.raises(ValueError, match="拒绝原因不能为空"):
            await record_reject_audit(
                db=db,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                log_id=uuid.uuid4(),
                reject_reason="",
            )

    @pytest.mark.asyncio
    async def test_reject_requires_non_whitespace_reason(self):
        """拒绝原因不能只有空白"""
        db = AsyncMock()
        with pytest.raises(ValueError, match="拒绝原因不能为空"):
            await record_reject_audit(
                db=db,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                log_id=uuid.uuid4(),
                reject_reason="   ",
            )


# ---------------------------------------------------------------------------
# 5.4: 来源摘要跳转
# ---------------------------------------------------------------------------


class TestSourceJumpLinks:
    """Task 5.4: 来源摘要可跳转到字段来源或工作包卡片。"""

    def test_build_source_jump_links(self):
        """为每个来源生成跳转链接"""
        source_summary = {
            "sources": [
                {"type": "audit_sheet", "label": "审定表", "available": True},
                {"type": "program_status", "label": "程序状态", "available": True},
                {"type": "confirmation", "label": "函证摘要", "available": True},
            ],
        }
        project_id = "proj-001"
        wp_id = "wp-001"

        links = build_source_jump_links(source_summary, project_id, wp_id)

        assert len(links) == 3
        assert links[0]["type"] == "audit_sheet"
        assert "sheet=audit_sheet" in links[0]["jump_target"]
        assert links[1]["type"] == "program_status"
        assert "sheet=program_status" in links[1]["jump_target"]
        assert links[2]["type"] == "confirmation"
        assert "sheet=confirmation" in links[2]["jump_target"]

    def test_all_source_types_have_jump_targets(self):
        """所有已知来源类型都有跳转链接"""
        source_summary = {
            "sources": [
                {"type": "audit_sheet", "label": "审定表", "available": True},
                {"type": "program_status", "label": "程序状态", "available": True},
                {"type": "field_sources", "label": "字段来源", "available": True},
                {"type": "adjustment_impact", "label": "调整影响", "available": True},
                {"type": "confirmation", "label": "函证摘要", "available": True},
                {"type": "bad_debt_ecl", "label": "坏账/ECL", "available": True},
                {"type": "analysis", "label": "分析程序", "available": True},
            ],
        }

        links = build_source_jump_links(source_summary, "proj", "wp")

        for link in links:
            assert link["jump_target"] is not None, f"{link['type']} 缺少跳转链接"


# ---------------------------------------------------------------------------
# 5.5: 治理面板跳转回 D1-C / D2-C
# ---------------------------------------------------------------------------


class TestGovernanceJumpLink:
    """Task 5.5: AI content log 治理面板可按目标绑定跳转回 D1-C / D2-C。"""

    def test_build_governance_jump_link(self):
        """从目标绑定构建跳转链接"""
        target_binding = {
            "account_package_id": "D1_fixed_assets",
            "wp_id": "wp-123",
            "sheet_type": "conclusion",
            "field_id": "d1.conclusion.overall",
        }
        link = build_governance_jump_link(target_binding, "proj-001")

        assert "/projects/proj-001/workpapers/wp-123" in link
        assert "sheet=conclusion" in link
        assert "field=d1.conclusion.overall" in link

    def test_jump_link_for_d2_conclusion(self):
        """D2-C 跳转链接"""
        target_binding = {
            "account_package_id": "D2_accounts_receivable",
            "wp_id": "wp-456",
            "sheet_type": "conclusion",
            "field_id": "d2.conclusion.overall",
        }
        link = build_governance_jump_link(target_binding, "proj-002")

        assert "wp-456" in link
        assert "d2.conclusion.overall" in link


# ---------------------------------------------------------------------------
# 5.6: 按目标绑定过滤并跳转
# ---------------------------------------------------------------------------


class TestQueryByBinding:
    """Task 5.6: AI content log 查询可按 account_package_id、wp_id、field_id 过滤并跳转。"""

    @pytest.mark.asyncio
    async def test_query_by_wp_id(self):
        """按 wp_id 过滤"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 模拟返回一条记录
        log = MagicMock()
        log.id = uuid.uuid4()
        log.wp_id = wp_id
        log.target_cell = f"workpaper:{wp_id}:d1.conclusion.overall"
        log.model = "qwen3.5-27b"
        log.confirm_action = "pending"
        log.generated_content = "AI 草稿内容"
        log.revised_content = None
        log.confirmed_by = None
        log.confirmed_at = None
        log.generated_at = MagicMock()
        log.generated_at.isoformat.return_value = "2026-01-01T00:00:00"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        db.execute = AsyncMock(return_value=mock_result)

        results = await query_ai_content_logs_by_binding(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
        )

        assert len(results) == 1
        assert results[0]["wp_id"] == str(wp_id)
        assert results[0]["field_id"] == "d1.conclusion.overall"
        assert "jump_link" in results[0]

    @pytest.mark.asyncio
    async def test_query_by_field_id_filters(self):
        """按 field_id 过滤只返回匹配记录"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        # 两条记录，不同 field_id
        log1 = MagicMock()
        log1.id = uuid.uuid4()
        log1.wp_id = wp_id
        log1.target_cell = f"workpaper:{wp_id}:d1.conclusion.overall"
        log1.model = "qwen3.5-27b"
        log1.confirm_action = "confirmed"
        log1.generated_content = "结论1"
        log1.revised_content = None
        log1.confirmed_by = uuid.uuid4()
        log1.confirmed_at = MagicMock()
        log1.confirmed_at.isoformat.return_value = "2026-01-01T01:00:00"
        log1.generated_at = MagicMock()
        log1.generated_at.isoformat.return_value = "2026-01-01T00:00:00"

        log2 = MagicMock()
        log2.id = uuid.uuid4()
        log2.wp_id = wp_id
        log2.target_cell = f"workpaper:{wp_id}:d1.conclusion.other_field"
        log2.model = "qwen3.5-27b"
        log2.confirm_action = "pending"
        log2.generated_content = "结论2"
        log2.revised_content = None
        log2.confirmed_by = None
        log2.confirmed_at = None
        log2.generated_at = MagicMock()
        log2.generated_at.isoformat.return_value = "2026-01-01T00:30:00"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log1, log2]
        db.execute = AsyncMock(return_value=mock_result)

        # 只查 overall 字段
        results = await query_ai_content_logs_by_binding(
            db=db,
            project_id=project_id,
            field_id="d1.conclusion.overall",
        )

        assert len(results) == 1
        assert results[0]["field_id"] == "d1.conclusion.overall"

    @pytest.mark.asyncio
    async def test_query_result_includes_jump_link(self):
        """查询结果包含跳转链接"""
        db = AsyncMock()
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        log = MagicMock()
        log.id = uuid.uuid4()
        log.wp_id = wp_id
        log.target_cell = f"workpaper:{wp_id}:d2.conclusion.overall"
        log.model = "qwen3.5-27b"
        log.confirm_action = "confirmed"
        log.generated_content = "D2 结论"
        log.revised_content = None
        log.confirmed_by = uuid.uuid4()
        log.confirmed_at = MagicMock()
        log.confirmed_at.isoformat.return_value = "2026-01-01T01:00:00"
        log.generated_at = MagicMock()
        log.generated_at.isoformat.return_value = "2026-01-01T00:00:00"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log]
        db.execute = AsyncMock(return_value=mock_result)

        results = await query_ai_content_logs_by_binding(
            db=db,
            project_id=project_id,
            wp_id=wp_id,
        )

        assert len(results) == 1
        jump_link = results[0]["jump_link"]
        assert str(wp_id) in jump_link
        assert "d2.conclusion.overall" in jump_link
        assert "conclusion" in jump_link
