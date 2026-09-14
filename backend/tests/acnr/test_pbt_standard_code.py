r"""Property-based test for standard wp_code convergence.

# Feature: acnr, Property 9: 标准码判定收敛（J1/S3 判为标准，[A-I]\d 误判消除）

**Validates: Requirements 12.4, 12.5**

验证 is_standard_wp_code() 单一函数：
1. 所有匹配 ^[A-S]\d 的 wp_code 判为标准底稿（含旧 [A-I]\d 误判盲区的 J~S）
2. 自定义 wp_code（CUST-01、GT_Custom 等）不被判为标准
3. 结果一致、幂等
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.grammar import is_standard_wp_code  # noqa: E402

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 标准码策略：[A-S] 开头 + 至少一位数字 + 可选后缀
_standard_letter = st.sampled_from(list("ABCDEFGHIJKLMNOPQRS"))
_digit = st.sampled_from(list("0123456789"))
_suffix = st.text(
    alphabet=st.sampled_from(list("0123456789-abcdefABCDEF")),
    min_size=0,
    max_size=6,
)

standard_wp_code_strategy = st.builds(
    lambda letter, digit, suffix: f"{letter}{digit}{suffix}",
    _standard_letter,
    _digit,
    _suffix,
)

# 自定义码策略：确保不以 [A-S]\d 开头
_custom_prefixes = st.sampled_from([
    "CUST-", "GT_", "custom_", "ZZ-", "T-", "U-", "V-", "W-", "X-", "Y-",
    "Z-", "0-", "1-", "test-", "my-",
])
_custom_suffix = st.text(
    alphabet=st.sampled_from(list("0123456789abcdefghijklmnop-_")),
    min_size=1,
    max_size=8,
)

custom_wp_code_strategy = st.builds(
    lambda prefix, suffix: f"{prefix}{suffix}",
    _custom_prefixes,
    _custom_suffix,
)


# ---------------------------------------------------------------------------
# Property Test
# ---------------------------------------------------------------------------


class TestStandardCodeConvergence:
    """Property 9: 标准码判定收敛（J1/S3 判为标准，[A-I]\\d 误判消除）。

    **Validates: Requirements 12.4, 12.5**
    """

    @settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(wp_code=standard_wp_code_strategy)
    def test_standard_codes_judged_as_standard(self, wp_code: str):
        """所有 ^[A-S]\\d 的 wp_code 判为标准底稿。

        Property: ∀ wp_code matching ^[A-S]\\d → is_standard_wp_code(wp_code) == True
        R12.4: J1/S3 判为标准底稿。
        R12.5: 消除旧 [A-I]\\d 误判（J~S 循环也是标准）。
        """
        assert is_standard_wp_code(wp_code), (
            f"wp_code='{wp_code}' 匹配 ^[A-S]\\d 但未被判定为标准底稿"
        )

    @settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(wp_code=custom_wp_code_strategy)
    def test_custom_codes_not_judged_as_standard(self, wp_code: str):
        """自定义码（CUST-01、GT_Custom 等）不被判为标准。

        Property: ∀ wp_code ∉ ^[A-S]\\d → is_standard_wp_code(wp_code) == False
        R12.5: 非 [A-S]\\d 开头的码不应被误判为标准底稿。
        """
        assert not is_standard_wp_code(wp_code), (
            f"wp_code='{wp_code}' 不匹配 ^[A-S]\\d 但被误判为标准底稿"
        )

    @settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(wp_code=standard_wp_code_strategy)
    def test_consistent_results(self, wp_code: str):
        """is_standard_wp_code() 结果幂等一致。

        Property: ∀ wp_code → is_standard_wp_code(wp_code) == is_standard_wp_code(wp_code)
        """
        result1 = is_standard_wp_code(wp_code)
        result2 = is_standard_wp_code(wp_code)
        assert result1 == result2, (
            f"wp_code='{wp_code}' 两次调用结果不一致: {result1} vs {result2}"
        )
