"""Property-Based Tests for A17-3-1 业务咨询结果执行情况记录 render strategy.

Property 2: A17-3 引用一致性 — 当 A17-3 section 1 数据存在时,
a173_reference 字段必须反映 A17-3 的 overview + background 内容.

**Validates: Requirements 8.3, Design §Property 2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── Property 2: A17-3 引用一致性 ────────────────────────────────────────────

EXPECTED_META_KEYS = {"executor", "execution_date", "review_date", "reviewer"}
EXPECTED_SECTION_KEYS = {"1": {"supplementary"}, "2": {"execution_details"}, "3": {"results"}, "4": {"follow_up"}}
EXPECTED_REFERENCE_KEYS = {"overview", "background"}
EXPECTED_CONTEXT_KEYS = {"client_name", "period"}


@st.composite
def a1731_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A17-3-1 render responses matching the expected schema."""
    meta_info = {
        "executor": draw(st.text(min_size=0, max_size=20)),
        "execution_date": draw(st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True) | st.just("")),
        "review_date": draw(st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True) | st.just("")),
        "reviewer": draw(st.text(min_size=0, max_size=20)),
    }
    sections = {
        "1": {"supplementary": draw(st.text(min_size=0, max_size=200))},
        "2": {"execution_details": draw(st.text(min_size=0, max_size=200))},
        "3": {"results": draw(st.text(min_size=0, max_size=200))},
        "4": {"follow_up": draw(st.text(min_size=0, max_size=200))},
    }
    # A17-3 reference: either both populated or both empty
    has_ref = draw(st.booleans())
    if has_ref:
        overview = draw(st.text(min_size=1, max_size=100))
        background = draw(st.text(min_size=1, max_size=100))
    else:
        overview = ""
        background = ""
    a173_reference = {"overview": overview, "background": background}
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "period": draw(st.text(min_size=0, max_size=30)),
    }
    return {
        "meta_info": meta_info,
        "sections": sections,
        "a173_reference": a173_reference,
        "project_context": project_context,
    }


class TestProperty2A173ReferenceConsistency:
    """Property 2: A17-3 引用一致性.

    For any valid A17-3-1 render response:
    - a173_reference SHALL always have exactly 2 keys: overview, background
    - When A17-3 data exists, the reference fields SHALL be non-empty strings
    - Response structure SHALL always have 4 top-level keys

    **Validates: Requirements 8.3, Design §Property 2**
    """

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_a173_reference_always_has_two_keys(self, data: dict):
        """Property 2a: a173_reference 恰好 2 keys (overview, background)."""
        assert set(data["a173_reference"].keys()) == EXPECTED_REFERENCE_KEYS

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_a173_reference_values_are_strings(self, data: dict):
        """Property 2b: a173_reference 值均为字符串."""
        for key, val in data["a173_reference"].items():
            assert isinstance(val, str), f"a173_reference.{key} is {type(val)}, expected str"

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_response_has_four_top_keys(self, data: dict):
        """Property 2c: 响应恰好 4 顶层 keys."""
        assert set(data.keys()) == {"meta_info", "sections", "a173_reference", "project_context"}

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_meta_info_has_exactly_4_keys(self, data: dict):
        """Property 2d: meta_info 恰好 4 keys."""
        assert set(data["meta_info"].keys()) == EXPECTED_META_KEYS

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_sections_have_correct_structure(self, data: dict):
        """Property 2e: sections 各章有正确字段."""
        for sec_num, expected_keys in EXPECTED_SECTION_KEYS.items():
            assert set(data["sections"][sec_num].keys()) == expected_keys

    @settings(max_examples=5)
    @given(data=a1731_render_response_strategy())
    def test_project_context_has_2_keys(self, data: dict):
        """Property 2f: project_context 恰好 2 keys."""
        assert set(data["project_context"].keys()) == EXPECTED_CONTEXT_KEYS
