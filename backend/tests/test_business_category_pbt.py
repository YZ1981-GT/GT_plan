"""业务分类过滤 PBT

Property: 对任意业务分类，A 类专属底稿仅在 A 类项目中 applicable=True，C 类必为 False。
B 类保留 A24/A25 但排除 A26。

max_examples=5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.business_category_service import (
    get_category_prefix,
    get_template_list_with_applicability,
    is_template_applicable,
    invalidate_cache,
)

# A 类专属底稿编码
A_ONLY_CODES = {"A1-12", "A1-16", "A17", "A17-5", "A18", "A27", "A28"}
# A26 也是 A 类专属
A26_CODES = {"A26"}
# A24/A25 是 A+B 类（B 类也需要质控复核）
AB_CODES = {"A24-1", "A24-2", "A25-1", "A25-2"}


category_st = st.sampled_from([
    "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8",
    "B1", "B2", "B3", "B4", "B5", "B6",
    "C",
])


def setup_module():
    invalidate_cache()


@given(category=category_st)
@settings(max_examples=5, deadline=None)
def test_a_only_templates_not_applicable_for_c(category):
    """Property: C 类项目中 A 类专属底稿 applicable=False"""
    prefix = get_category_prefix(category)
    templates = get_template_list_with_applicability(category)

    for t in templates:
        code = t.get("wp_code", "")
        if code in A_ONLY_CODES or code in A26_CODES:
            if prefix == "C":
                assert t["applicable"] is False, f"{code} should not be applicable for C"
            elif prefix == "A":
                assert t["applicable"] is True, f"{code} should be applicable for A"


@given(category=st.sampled_from(["B1", "B2", "B3", "B4", "B5", "B6"]))
@settings(max_examples=5, deadline=None)
def test_b_category_keeps_quality_review(category):
    """Property: B 类保留 A24/A25（质控复核）"""
    templates = get_template_list_with_applicability(category)
    for t in templates:
        code = t.get("wp_code", "")
        if code in AB_CODES:
            assert t["applicable"] is True, f"{code} should be applicable for B"


@given(category=st.sampled_from(["B1", "B2", "B3", "B4", "B5", "B6"]))
@settings(max_examples=5, deadline=None)
def test_b_category_excludes_a26(category):
    """Property: B 类排除 A26（专委会）"""
    templates = get_template_list_with_applicability(category)
    for t in templates:
        code = t.get("wp_code", "")
        if code in A26_CODES:
            assert t["applicable"] is False, f"A26 should not be applicable for B"


def test_get_category_prefix():
    """get_category_prefix 正确提取"""
    assert get_category_prefix("A3") == "A"
    assert get_category_prefix("B1") == "B"
    assert get_category_prefix("C") == "C"
    assert get_category_prefix("") == "C"
    assert get_category_prefix("a2") == "A"
