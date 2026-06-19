# Feature: workpaper-editing-guidance, Property 11: 复杂度分类确定性
"""Property 11: 复杂度分类确定性

For any wp_code, classify_complexity returns same value on multiple calls (deterministic).
Return value is always one of "high"/"medium"/"low".
Known high codes (A17/B60/*-1/*A) always return "high".

**Validates: Requirements 7.1**
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_guidance_service import GuidanceService


# 任意 wp_code
_wp_code_strategy = st.from_regex(r"[A-Z][A-Z0-9\-]{0,8}", fullmatch=True)

# 已知高复杂度 wp_code
_known_high_codes = st.sampled_from([
    "A17", "B60", "B50", "B51",  # 精确匹配
    "D2-1", "E1-1", "F1-1", "N2-1",  # *-1 模式
    "D0A", "E1A", "F0A",  # *A 模式
])

_VALID_COMPLEXITY = {"high", "medium", "low"}


@given(wp_code=_wp_code_strategy)
@settings(max_examples=5)
def test_classify_complexity_is_deterministic(wp_code: str):
    """对任意 wp_code，classify_complexity 多次调用结果一致（确定性）。"""
    svc = GuidanceService()

    results = [svc.classify_complexity(wp_code) for _ in range(3)]

    # 所有调用结果相同
    assert len(set(results)) == 1, (
        f"wp_code={wp_code} 多次调用结果不一致: {results}"
    )


@given(wp_code=_wp_code_strategy)
@settings(max_examples=5)
def test_classify_complexity_returns_valid_literal(wp_code: str):
    """返回值永远是 high/medium/low 之一。"""
    svc = GuidanceService()
    result = svc.classify_complexity(wp_code)

    assert result in _VALID_COMPLEXITY, (
        f"wp_code={wp_code} 返回了非法复杂度: {result}"
    )


@given(wp_code=_known_high_codes)
@settings(max_examples=5)
def test_known_high_codes_return_high(wp_code: str):
    """已知高复杂度码（A17/B60/B50/B51/*-1/*A）必须返回 "high"。"""
    svc = GuidanceService()
    result = svc.classify_complexity(wp_code)

    assert result == "high", (
        f"已知高复杂度 wp_code={wp_code} 应返回 'high'，实际为 '{result}'"
    )
