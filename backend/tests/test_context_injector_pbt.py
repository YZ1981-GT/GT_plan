# Feature: workpaper-editing-guidance, Properties 7, 8, 9, 10 — ContextInjector
"""Properties 7, 8, 9, 10 — ContextInjector

Property 7: build_system_prompt output contains wp_code, wp_name, client_name, audit_period
Property 8: _truncate_to_tokens output length ≤ max_tokens * 2 characters, truncation at line boundary
Property 9: determination table (*-1) summary contains "科目"+"金额";
            program table (*A) summary contains "已完成"+"步骤"
Property 10: merge_system_messages output has at most 1 system message

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.context_injector import ContextInjector, WpChatContext


# ---------------------------------------------------------------------------
# Property 7: 上下文注入完整性
# ---------------------------------------------------------------------------

_chinese_text = st.text(
    alphabet=st.sampled_from("测试公司客户审计年度内容名称"),
    min_size=2,
    max_size=10,
)

_wp_code_st = st.from_regex(r"[A-Z][0-9\-A]{1,5}", fullmatch=True)


@given(
    wp_code=_wp_code_st,
    wp_name=_chinese_text,
    client_name=_chinese_text,
    audit_period=st.from_regex(r"20[12][0-9]-\d{2}-\d{2} 至 20[12][0-9]-\d{2}-\d{2}", fullmatch=True),
)
@settings(max_examples=5)
def test_build_system_prompt_contains_context_fields(
    wp_code: str, wp_name: str, client_name: str, audit_period: str
):
    """build_system_prompt 输出必须包含 wp_code、wp_name、client_name、audit_period 的实际值。"""
    ctx = WpChatContext(
        wp_code=wp_code,
        wp_name=wp_name,
        component_type="d-form-table",
        client_name=client_name,
        audit_period=audit_period,
        business_category="C",
        guidance_text="编制说明测试文本",
        filled_data_summary="已填数据摘要",
    )

    injector = ContextInjector()
    prompt = injector.build_system_prompt(ctx)

    assert wp_code in prompt, f"prompt 中未包含 wp_code={wp_code}"
    assert wp_name in prompt, f"prompt 中未包含 wp_name={wp_name}"
    assert client_name in prompt, f"prompt 中未包含 client_name={client_name}"
    assert audit_period in prompt, f"prompt 中未包含 audit_period={audit_period}"


# ---------------------------------------------------------------------------
# Property 8: 已填数据摘要截断不超限
# ---------------------------------------------------------------------------

# 生成多行中文文本
_multiline_text = st.lists(
    st.text(alphabet=st.sampled_from("中文内容字段值测试数据科目金额"), min_size=5, max_size=50),
    min_size=1,
    max_size=100,
).map(lambda lines: "\n".join(lines))

_max_tokens_st = st.integers(min_value=10, max_value=500)


@given(text=_multiline_text, max_tokens=_max_tokens_st)
@settings(max_examples=5)
def test_truncate_to_tokens_respects_limit(text: str, max_tokens: int):
    """_truncate_to_tokens 输出长度 ≤ max_tokens * 2 字符，且截断在行边界。"""
    injector = ContextInjector()
    result = injector._truncate_to_tokens(text, max_tokens=max_tokens)

    max_chars = max_tokens * 2
    assert len(result) <= max_chars, (
        f"截断后长度 {len(result)} 超过上限 {max_chars} (max_tokens={max_tokens})"
    )

    # 如果发生了截断，验证截断在行边界（结果不包含半截行）
    if len(result) < len(text) and result:
        # 结果的最后一个字符应该是原文中某行的末尾
        # 即 result 应该是 text 按行截取的前若干完整行
        result_lines = result.split("\n")
        text_lines = text.split("\n")
        # 前 N 行应该完全匹配
        for i, line in enumerate(result_lines):
            if i < len(text_lines):
                assert line == text_lines[i], f"第 {i} 行不匹配，截断未在行边界"


# ---------------------------------------------------------------------------
# Property 9: 上下文按底稿类型适配
# ---------------------------------------------------------------------------

# 审定表 wp_code（以 -1 结尾）
_determination_wp_codes = st.from_regex(r"[D-N]\d+-1", fullmatch=True)
# 程序表 wp_code（以 A 结尾）
_program_wp_codes = st.from_regex(r"[D-N]\d+A", fullmatch=True)


@given(wp_code=_determination_wp_codes)
@settings(max_examples=5)
def test_determination_table_summary_contains_keywords(wp_code: str):
    """审定表类底稿（*-1），已填数据摘要包含「科目」和「金额」关键词。"""
    injector = ContextInjector()
    wp_data = {
        "rows": [
            {"account_name": "应收账款", "audited_amount": 500000},
            {"account_name": "预付账款", "audited_amount": 200000},
        ]
    }

    result = injector._build_filled_data_summary(wp_code, "d-form-table", wp_data)

    assert "科目" in result, f"wp_code={wp_code} 审定表摘要应包含「科目」"
    assert "金额" in result, f"wp_code={wp_code} 审定表摘要应包含「金额」"


@given(wp_code=_program_wp_codes)
@settings(max_examples=5)
def test_program_table_summary_contains_keywords(wp_code: str):
    """程序表类底稿（*A），已填数据摘要包含「已完成」和「步骤」关键词。"""
    injector = ContextInjector()
    wp_data = {
        "steps": [
            {"name": "步骤1", "completed": True},
            {"name": "步骤2", "completed": False},
            {"name": "步骤3", "completed": True},
        ]
    }

    result = injector._build_filled_data_summary(wp_code, "a-program-console", wp_data)

    assert "已完成" in result, f"wp_code={wp_code} 程序表摘要应包含「已完成」"
    assert "步骤" in result, f"wp_code={wp_code} 程序表摘要应包含「步骤」"


# ---------------------------------------------------------------------------
# Property 10: 单条 system 消息输出
# ---------------------------------------------------------------------------

# 生成随机消息列表
_roles = st.sampled_from(["system", "user", "assistant"])
_message = st.fixed_dictionaries({
    "role": _roles,
    "content": st.text(min_size=1, max_size=50),
})
_messages_list = st.lists(_message, min_size=1, max_size=10)


@given(messages=_messages_list)
@settings(max_examples=5)
def test_merge_system_messages_at_most_one_system(messages: list[dict]):
    """merge_system_messages 处理后，role=system 的消息最多一条。"""
    result = ContextInjector.merge_system_messages(messages)

    system_count = sum(1 for m in result if m.get("role") == "system")
    assert system_count <= 1, (
        f"合并后仍有 {system_count} 条 system 消息（应 ≤ 1）"
    )
