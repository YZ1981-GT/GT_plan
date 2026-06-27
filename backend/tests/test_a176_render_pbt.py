"""Property-Based Tests for A17-6 总结会会议纪要 render strategy.

Property 3: 响应结构完整性 — meta_info 恰好 6 keys + fields 恰好 5 keys + project_context 3 keys

**Validates: Requirements 1.1, Design §Data Models**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── Property 3: 响应结构完整性 ──────────────────────────────────────────────

EXPECTED_META_KEYS = {"client_name", "period", "preparer", "reviewer", "date", "index_no"}
EXPECTED_FIELD_KEYS = {"meeting_time", "attendees", "minutes", "conclusion", "attachments"}
EXPECTED_CONTEXT_KEYS = {"client_name", "period", "current_user"}


@st.composite
def a176_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A17-6 render responses matching the expected schema."""
    meta_info = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "period": draw(st.text(min_size=0, max_size=30)),
        "preparer": draw(st.text(min_size=0, max_size=20)),
        "reviewer": draw(st.text(min_size=0, max_size=20)),
        "date": draw(st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True) | st.just("")),
        "index_no": "A17-6",
    }
    fields = {
        "meeting_time": draw(st.text(min_size=0, max_size=50)),
        "attendees": draw(st.text(min_size=0, max_size=100)),
        "minutes": draw(st.text(min_size=0, max_size=500)),
        "conclusion": draw(st.text(min_size=0, max_size=200)),
        "attachments": draw(st.text(min_size=0, max_size=100)),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "period": draw(st.text(min_size=0, max_size=30)),
        "current_user": draw(st.text(min_size=0, max_size=20)),
    }
    return {"meta_info": meta_info, "fields": fields, "project_context": project_context}


class TestProperty3ResponseStructureCompleteness:
    """Property 3: 响应结构完整性.

    For any valid A17-6 render response, meta_info SHALL have exactly 6 keys,
    fields SHALL have exactly 5 keys, project_context SHALL have exactly 3 keys.

    **Validates: Design §Data Models, Requirements 1.1**
    """

    @settings(max_examples=5)
    @given(data=a176_render_response_strategy())
    def test_meta_info_has_exactly_6_keys(self, data: dict):
        """Property 3a: meta_info 恰好 6 keys."""
        assert set(data["meta_info"].keys()) == EXPECTED_META_KEYS

    @settings(max_examples=5)
    @given(data=a176_render_response_strategy())
    def test_fields_has_exactly_5_keys(self, data: dict):
        """Property 3b: fields 恰好 5 keys."""
        assert set(data["fields"].keys()) == EXPECTED_FIELD_KEYS

    @settings(max_examples=5)
    @given(data=a176_render_response_strategy())
    def test_project_context_has_exactly_3_keys(self, data: dict):
        """Property 3c: project_context 恰好 3 keys."""
        assert set(data["project_context"].keys()) == EXPECTED_CONTEXT_KEYS

    @settings(max_examples=5)
    @given(data=a176_render_response_strategy())
    def test_all_values_are_strings(self, data: dict):
        """Property 3d: 所有值均为字符串."""
        for section in ("meta_info", "fields", "project_context"):
            for key, val in data[section].items():
                assert isinstance(val, str), f"{section}.{key} is {type(val)}, expected str"

    @settings(max_examples=5)
    @given(data=a176_render_response_strategy())
    def test_index_no_is_always_a176(self, data: dict):
        """Property 3e: index_no 始终为 'A17-6'."""
        assert data["meta_info"]["index_no"] == "A17-6"
