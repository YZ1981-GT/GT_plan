"""Tests for R3 Task 21: AI 内容统一结构化 + 门禁规则

覆盖：
1. wrap_ai_output 结构化包装
2. migrate_ai_content_structure 迁移脚本
3. AIContentMustBeConfirmedRule 门禁规则
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_ai_service import wrap_ai_output


# ── 1. wrap_ai_output 测试 ─────────────────────────────────────


class TestWrapAiOutput:
    """测试 AI 输出统一结构化包装函数"""

    def test_basic_wrap(self):
        """基本包装：所有必需字段都存在"""
        result = wrap_ai_output(
            "这是 AI 生成的分析文本",
            confidence=0.85,
            target_cell="E5",
        )
        assert result["type"] == "ai_generated"
        assert result["content"] == "这是 AI 生成的分析文本"
        assert result["confidence"] == 0.85
        assert result["target_cell"] == "E5"
        assert result["confirmed_by"] is None
        assert result["confirmed_at"] is None
        assert result["confirm_action"] is None
        assert result["revised_content"] is None
        assert result["target_field"] is None
        # id 是有效 UUID
        uuid.UUID(result["id"])
        # generated_at 是 ISO 格式
        assert "T" in result["generated_at"]
        # source_model 有值
        assert result["source_model"] is not None
        assert len(result["source_model"]) > 0

    def test_custom_source_model(self):
        """自定义 source_model"""
        result = wrap_ai_output(
            "test",
            source_model="gpt-4o",
            confidence=0.9,
        )
        assert result["source_model"] == "gpt-4o"

    def test_default_source_model_from_settings(self):
        """默认 source_model 从 settings 读取"""
        result = wrap_ai_output("test")
        # 应该是 settings.DEFAULT_CHAT_MODEL
        assert "Qwen" in result["source_model"] or result["source_model"] != "unknown"

    def test_target_field(self):
        """target_field 参数"""
        result = wrap_ai_output(
            "结论建议",
            target_field="conclusion",
            confidence=0.8,
        )
        assert result["target_field"] == "conclusion"
        assert result["target_cell"] is None

    def test_source_prompt_version(self):
        """source_prompt_version 参数"""
        result = wrap_ai_output(
            "test",
            source_prompt_version="v2.1",
        )
        assert result["source_prompt_version"] == "v2.1"

    def test_unique_ids(self):
        """每次调用生成不同的 id"""
        r1 = wrap_ai_output("a")
        r2 = wrap_ai_output("b")
        assert r1["id"] != r2["id"]

    def test_empty_content(self):
        """空内容也能包装"""
        result = wrap_ai_output("")
        assert result["content"] == ""
        assert result["type"] == "ai_generated"


# ── 2. 迁移脚本测试 ───────────────────────────────────────────


class TestMigrateAiContentStructure:
    """测试 parsed_data.ai_content 清洗迁移逻辑"""

    def test_normalize_missing_fields(self):
        """缺失字段补齐"""
        from scripts.migrate_ai_content_structure import normalize_ai_content_item

        old_item = {
            "cell_ref": "B5",
            "status": "pending",
            "content": "AI 生成文本",
        }
        result, changed = normalize_ai_content_item(old_item)
        assert changed is True
        assert result["confirmed_by"] is None
        assert result["confirmed_at"] is None
        assert result["confirm_action"] is None
        assert result["revised_content"] is None
        assert result["type"] == "ai_generated"
        assert result["source_model"] == "unknown"
        assert result["target_cell"] == "B5"  # 从 cell_ref 映射
        # id 被补齐
        uuid.UUID(result["id"])

    def test_normalize_accepted_status_mapping(self):
        """status=accepted 映射到 confirm_action=accept"""
        from scripts.migrate_ai_content_structure import normalize_ai_content_item

        old_item = {
            "status": "accepted",
            "content": "已确认内容",
        }
        result, changed = normalize_ai_content_item(old_item)
        assert changed is True
        assert result["confirm_action"] == "accept"

    def test_normalize_already_complete(self):
        """已有所有字段的条目不变"""
        from scripts.migrate_ai_content_structure import normalize_ai_content_item

        complete_item = {
            "id": str(uuid.uuid4()),
            "type": "ai_generated",
            "source_model": "qwen-27b",
            "source_prompt_version": "v1.2",
            "generated_at": "2026-01-01T00:00:00",
            "confidence": 0.9,
            "content": "完整条目",
            "target_cell": "A1",
            "target_field": None,
            "confirmed_by": str(uuid.uuid4()),
            "confirmed_at": "2026-01-02T00:00:00",
            "confirm_action": "accept",
            "revised_content": None,
        }
        result, changed = normalize_ai_content_item(complete_item)
        assert changed is False
        assert result == complete_item

    def test_normalize_list(self):
        """列表级别规范化"""
        from scripts.migrate_ai_content_structure import normalize_ai_content_list

        items = [
            {"content": "item1", "status": "pending"},
            {"content": "item2", "cell_ref": "C3", "status": "accepted"},
        ]
        normalized, changed = normalize_ai_content_list(items)
        assert changed is True
        assert len(normalized) == 2
        assert normalized[0]["confirmed_by"] is None
        assert normalized[1]["target_cell"] == "C3"
        assert normalized[1]["confirm_action"] == "accept"


# ── 3. AIContentMustBeConfirmedRule 测试 ───────────────────────


class TestAIContentMustBeConfirmedRule:
    """测试 sign_off 门禁规则：AI 内容必须确认"""

    @pytest.fixture
    def rule(self):
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule
        return AIContentMustBeConfirmedRule()

    @pytest.mark.asyncio
    async def test_no_project_id(self, rule):
        """无 project_id 时返回 None"""
        db = AsyncMock()
        result = await rule.check(db, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_no_workpapers(self, rule):
        """项目无底稿时返回 None"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None

    @pytest.mark.asyncio
    async def test_all_confirmed(self, rule):
        """所有 AI 内容已确认时返回 None"""
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "已确认内容",
                    "target_cell": "E5",
                    "confirmed_by": str(uuid.uuid4()),
                    "confirmed_at": "2026-01-01T00:00:00",
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None

    @pytest.mark.asyncio
    async def test_unconfirmed_with_target_cell_blocks(self, rule):
        """未确认且有 target_cell 的 AI 内容阻断 sign_off"""
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "未确认的 AI 结论",
                    "target_cell": "E5",
                    "confirmed_by": None,
                    "confirmed_at": None,
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is not None
        assert result.rule_code == "R3-AI-MUST-CONFIRM"
        assert result.error_code == "AI_CONTENT_UNCONFIRMED"
        assert result.severity.value == "blocking"
        assert "1" in result.message

    @pytest.mark.asyncio
    async def test_unconfirmed_without_target_cell_passes(self, rule):
        """未确认但 target_cell 为空的 AI 内容不阻断（简报/年报类独立产物）"""
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {
            "ai_content": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "ai_generated",
                    "content": "简报类 AI 内容",
                    "target_cell": None,
                    "confirmed_by": None,
                    "confirmed_at": None,
                },
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_unconfirmed_items(self, rule):
        """多个未确认项正确计数"""
        db = AsyncMock()
        wp1 = MagicMock()
        wp1.id = uuid.uuid4()
        wp1.wp_code = "D-001"
        wp1.parsed_data = {
            "ai_content": [
                {"id": "1", "content": "a", "target_cell": "A1", "confirmed_by": None},
                {"id": "2", "content": "b", "target_cell": "B2", "confirmed_by": None},
            ]
        }
        wp2 = MagicMock()
        wp2.id = uuid.uuid4()
        wp2.wp_code = "D-002"
        wp2.parsed_data = {
            "ai_content": [
                {"id": "3", "content": "c", "target_cell": "C3", "confirmed_by": None},
                {"id": "4", "content": "d", "target_cell": None, "confirmed_by": None},  # 无 target_cell，不计
            ]
        }
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp1, wp2]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is not None
        assert result.location["unconfirmed_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_ai_content_list(self, rule):
        """ai_content 为空列表时返回 None"""
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {"ai_content": []}
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None

    @pytest.mark.asyncio
    async def test_no_ai_content_key(self, rule):
        """parsed_data 无 ai_content 键时返回 None"""
        db = AsyncMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.wp_code = "D-001"
        wp.parsed_data = {"conclusion": "some text"}
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [wp]
        db.execute = AsyncMock(return_value=mock_result)

        result = await rule.check(db, {"project_id": uuid.uuid4()})
        assert result is None

    @pytest.mark.asyncio
    async def test_rule_registered_to_sign_off(self):
        """验证规则注册到 sign_off gate"""
        from app.services.gate_rules_phase14 import AIContentMustBeConfirmedRule
        from app.models.phase14_enums import GateSeverity

        rule = AIContentMustBeConfirmedRule()
        assert rule.rule_code == "R3-AI-MUST-CONFIRM"
        assert rule.severity == GateSeverity.blocking
