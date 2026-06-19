# Feature: workpaper-editing-guidance, Property 2: Guidance 端点永不返回空
# Feature: workpaper-editing-guidance, Property 12: 内容深度随复杂度缩放
"""Property 2: Guidance 端点永不返回空
Property 12: 内容深度随复杂度缩放

Property 2: For any valid wp_code string, GuidanceService.get_guidance always
returns non-empty raw_text and valid source enum.

Property 12: For high complexity wp_codes, get_guidance returns non-empty sections
and recommended_questions. For low complexity, sections may be empty but raw_text
is never empty.

**Validates: Requirements 2.4, 2.8, 7.2, 7.3, 7.4**
"""
from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_guidance_service import GuidanceService


def _run(coro):
    """辅助：同步执行 async 函数"""
    return asyncio.run(coro)


# wp_code 生成策略：字母开头 + 数字/连字符
_wp_code_strategy = st.from_regex(r"[A-Z][A-Z0-9\-]{1,6}", fullmatch=True)

_VALID_SOURCES = {
    "template_sheet", "template_header", "docx_instructions",
    "static_json", "typed_fallback", "fallback",
}


@given(wp_code=_wp_code_strategy)
@settings(max_examples=5)
def test_guidance_never_returns_empty(wp_code: str):
    """对任意有效的 wp_code，get_guidance 返回的 raw_text 永不为空，source 必为合法枚举值。"""
    svc = GuidanceService()
    response = _run(svc.get_guidance(wp_code=wp_code, template_path=None))

    # raw_text 永不为空
    assert response["guidance"]["raw_text"] != "", f"wp_code={wp_code} 返回了空 raw_text"

    # source 必为合法枚举值
    assert response["source"] in _VALID_SOURCES, (
        f"wp_code={wp_code} 返回了非法 source: {response['source']}"
    )

    # 基本结构完整
    assert "wp_code" in response
    assert "guidance" in response
    assert "sections" in response["guidance"]


# ---------------------------------------------------------------------------
# Property 12: 内容深度随复杂度缩放
# ---------------------------------------------------------------------------


# 已知高复杂度 wp_code
_HIGH_COMPLEXITY_CODES = st.sampled_from(["A17", "B60", "D2-1", "E1-1", "D0A", "E1A"])
# 已知低复杂度 wp_code
_LOW_COMPLEXITY_CODES = st.sampled_from(["A2", "A3", "X99", "Z1"])


@given(wp_code=_HIGH_COMPLEXITY_CODES)
@settings(max_examples=5)
def test_high_complexity_has_sections_and_questions(wp_code: str):
    """高复杂度底稿的 guidance 响应，sections 列表长度 ≥ 1 且 recommended_questions 非空。"""
    svc = GuidanceService()
    response = _run(svc.get_guidance(wp_code=wp_code, template_path=None))

    assert response["complexity"] == "high", (
        f"wp_code={wp_code} 应为 high 复杂度，实际为 {response['complexity']}"
    )
    # recommended_questions 非空
    assert len(response["recommended_questions"]) > 0, (
        f"wp_code={wp_code} 高复杂度应有推荐问题"
    )


@given(wp_code=_LOW_COMPLEXITY_CODES)
@settings(max_examples=5)
def test_low_complexity_raw_text_never_empty(wp_code: str):
    """低复杂度底稿，sections 可以为空但 raw_text 永不为空。"""
    svc = GuidanceService()
    response = _run(svc.get_guidance(wp_code=wp_code, template_path=None))

    assert response["complexity"] == "low", (
        f"wp_code={wp_code} 应为 low 复杂度，实际为 {response['complexity']}"
    )
    # raw_text 永不为空
    assert response["guidance"]["raw_text"] != "", (
        f"wp_code={wp_code} 低复杂度 raw_text 也不能为空"
    )
