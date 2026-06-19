"""ContextInjector 单元测试

验证：
1. build_system_prompt 返回非空字符串
2. _truncate_to_tokens 尊重 token 预算
3. merge_system_messages 合并正确
4. prompt 包含所有上下文字段
5. _build_filled_data_summary 按类型适配
"""

from __future__ import annotations

import pytest

from app.services.context_injector import ContextInjector, WpChatContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def injector():
    return ContextInjector()


@pytest.fixture
def sample_context():
    return WpChatContext(
        wp_code="D2-1",
        wp_name="主营业务收入审定表",
        component_type="d-form-table",
        client_name="测试公司",
        audit_period="2024-01-01 至 2024-12-31",
        business_category="C",
        guidance_text="一、编制目的\n确认收入金额的真实性\n二、步骤\n1. 获取明细账",
        filled_data_summary="审定表数据（前3行）：\n  科目: 主营收入, 金额: 1000000",
    )


# ---------------------------------------------------------------------------
# Test 1: build_system_prompt 返回非空字符串
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_returns_non_empty_string(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_wp_code(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "D2-1" in result

    def test_contains_wp_name(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "主营业务收入审定表" in result

    def test_contains_client_name(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "测试公司" in result

    def test_contains_audit_period(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "2024-01-01 至 2024-12-31" in result

    def test_contains_business_category(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "C" in result

    def test_contains_guidance_text(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "确认收入金额的真实性" in result

    def test_contains_filled_data_summary(self, injector, sample_context):
        result = injector.build_system_prompt(sample_context)
        assert "主营收入" in result

    def test_empty_guidance_shows_placeholder(self, injector):
        ctx = WpChatContext(
            wp_code="D2-1",
            wp_name="测试",
            component_type="d-form-table",
            client_name="客户",
            audit_period="2024",
            business_category="C",
            guidance_text="",
            filled_data_summary="",
        )
        result = injector.build_system_prompt(ctx)
        assert "暂无编制说明" in result
        assert "暂无已填数据" in result


# ---------------------------------------------------------------------------
# Test 2: _truncate_to_tokens 尊重 token 预算
# ---------------------------------------------------------------------------


class TestTruncateToTokens:
    def test_short_text_unchanged(self, injector):
        text = "短文本"
        result = injector._truncate_to_tokens(text, max_tokens=100)
        assert result == text

    def test_empty_text_returns_empty(self, injector):
        result = injector._truncate_to_tokens("", max_tokens=100)
        assert result == ""

    def test_long_text_truncated(self, injector):
        # 1 token ≈ 2 中文字符，max_tokens=10 → max_chars=20
        long_text = "这是第一行文本内容\n这是第二行文本内容\n这是第三行文本内容"
        result = injector._truncate_to_tokens(long_text, max_tokens=10)
        # max_chars = 20, 第一行 = 9 字符, 第二行 = 9 字符
        assert len(result) <= 20

    def test_truncation_at_line_boundary(self, injector):
        lines = ["第一行内容"] * 100  # 每行 4 字符
        text = "\n".join(lines)
        result = injector._truncate_to_tokens(text, max_tokens=10)
        # max_chars = 20, 每行 "第一行内容\n" = 5 字符
        # 结果应该是完整行，不在行中间断
        assert not result.endswith("第一行")  # 不在中间断

    def test_respects_max_tokens_budget(self, injector):
        """确保截断后字符数 ≤ max_tokens * 2"""
        long_text = "一二三四五六七八九十\n" * 200
        max_tokens = 50
        result = injector._truncate_to_tokens(long_text, max_tokens=max_tokens)
        assert len(result) <= max_tokens * 2


# ---------------------------------------------------------------------------
# Test 3: merge_system_messages 合并正确
# ---------------------------------------------------------------------------


class TestMergeSystemMessages:
    def test_single_system_unchanged(self, injector):
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "问题"},
        ]
        result = ContextInjector.merge_system_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "你是助手"
        assert result[1]["role"] == "user"

    def test_multiple_system_merged(self):
        messages = [
            {"role": "system", "content": "系统指令1"},
            {"role": "system", "content": "系统指令2"},
            {"role": "user", "content": "用户问题"},
            {"role": "assistant", "content": "回答"},
        ]
        result = ContextInjector.merge_system_messages(messages)
        # system 消息应合并为一条
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "系统指令1" in system_msgs[0]["content"]
        assert "系统指令2" in system_msgs[0]["content"]
        # 其他消息保持不变
        assert len(result) == 3  # 1 system + 1 user + 1 assistant

    def test_system_message_first(self):
        messages = [
            {"role": "user", "content": "用户问题"},
            {"role": "system", "content": "后置系统消息"},
        ]
        result = ContextInjector.merge_system_messages(messages)
        assert result[0]["role"] == "system"

    def test_no_system_messages(self):
        messages = [
            {"role": "user", "content": "问题"},
            {"role": "assistant", "content": "回答"},
        ]
        result = ContextInjector.merge_system_messages(messages)
        assert len(result) == 2
        assert all(m["role"] != "system" for m in result)

    def test_empty_system_content_skipped(self):
        messages = [
            {"role": "system", "content": ""},
            {"role": "system", "content": "有效内容"},
            {"role": "user", "content": "问题"},
        ]
        result = ContextInjector.merge_system_messages(messages)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "有效内容"


# ---------------------------------------------------------------------------
# Test 4: prompt 包含所有上下文字段
# ---------------------------------------------------------------------------


class TestPromptContainsAllFields:
    def test_all_fields_present(self, injector):
        ctx = WpChatContext(
            wp_code="E1-1",
            wp_name="货币资金审定表",
            component_type="d-form-table",
            client_name="深圳科技有限公司",
            audit_period="2025-01-01 至 2025-12-31",
            business_category="I",
            guidance_text="确认银行存款余额",
            filled_data_summary="已填写 5/8 个字段",
        )
        result = injector.build_system_prompt(ctx)
        assert "E1-1" in result
        assert "货币资金审定表" in result
        assert "d-form-table" in result
        assert "深圳科技有限公司" in result
        assert "2025-01-01 至 2025-12-31" in result
        assert "I" in result
        assert "确认银行存款余额" in result
        assert "已填写 5/8 个字段" in result


# ---------------------------------------------------------------------------
# Test 5: _build_filled_data_summary 按类型适配
# ---------------------------------------------------------------------------


class TestBuildFilledDataSummary:
    def test_determination_table(self, injector):
        """审定表（*-1）提取科目+金额"""
        wp_data = {
            "rows": [
                {"account_name": "主营业务收入", "audited_amount": 1000000},
                {"account_name": "其他业务收入", "audited_amount": 50000},
            ]
        }
        result = injector._build_filled_data_summary("D2-1", "d-form-table", wp_data)
        assert "科目" in result
        assert "金额" in result
        assert "主营业务收入" in result

    def test_program_table(self, injector):
        """程序表（*A）统计已完成步骤"""
        wp_data = {
            "steps": [
                {"name": "步骤1", "completed": True},
                {"name": "步骤2", "completed": False},
                {"name": "步骤3", "completed": True},
            ]
        }
        result = injector._build_filled_data_summary("D0A", "a-program-console", wp_data)
        assert "已完成" in result
        assert "步骤" in result
        assert "2/3" in result

    def test_generic_type(self, injector):
        """其他类型统计非空字段"""
        wp_data = {
            "field1": "value",
            "field2": "",
            "field3": None,
            "field4": "another",
        }
        result = injector._build_filled_data_summary("B60", "d-form-table", wp_data)
        assert "2/4" in result

    def test_none_data_returns_empty(self, injector):
        result = injector._build_filled_data_summary("D2-1", "d-form-table", None)
        assert result == ""

    def test_empty_dict_returns_empty(self, injector):
        result = injector._build_filled_data_summary("D2-1", "d-form-table", {})
        assert result == ""
