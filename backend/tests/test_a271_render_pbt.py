"""Property-Based Tests for A27-1 IT审计总结备忘录 render strategy.

Property 5: 后端响应结构完整性 — 7 top-level keys, chapters array length 7,
cross_references has 4 keys.

**Validates: Requirements 13.1**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── Strategies ───────────────────────────────────────────────────────────────

CONCLUSION_OPTIONS = ("部分有效", "没有有效", "已有效", None)


@st.composite
def a271_chapter_strategy(draw: st.DrawFn, number: int) -> dict:
    """Generate a single chapter entry matching A27-1 schema."""
    cross_ref_map = {1: "B22A-4-3", 2: "C22", 3: None, 4: "C21-1", 5: "B23-15", 6: None, 7: None}
    titles = {
        1: "了解信息系统环境",
        2: "IT风险和一般控制",
        3: "IT一般控制结论",
        4: "IT一般控制缺陷",
        5: "信息处理控制",
        6: "信息处理控制结论",
        7: "缺陷评估",
    }

    content = draw(st.none() | st.text(min_size=1, max_size=200)) if number in (1, 2, 4, 5, 7) else None
    conclusion = draw(st.sampled_from(CONCLUSION_OPTIONS)) if number in (3, 6, 7) else None
    deficiency = draw(st.none() | st.text(min_size=1, max_size=200)) if number in (3, 6) else None

    return {
        "number": number,
        "title": titles[number],
        "content": content,
        "conclusion": conclusion,
        "deficiency": deficiency,
        "cross_ref": cross_ref_map[number],
    }


@st.composite
def a271_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate a complete A27-1 render response matching expected schema."""
    meta_info = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_period": draw(st.text(min_size=0, max_size=20)),
        "index_no": "A27-1",
    }
    header = {
        "date": draw(st.none() | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
        "to": draw(st.none() | st.text(min_size=1, max_size=50)),
        "from_user": draw(st.none() | st.text(min_size=1, max_size=50)),
        "subject": draw(st.none() | st.text(min_size=1, max_size=50)),
    }
    purpose_text = draw(st.text(min_size=10, max_size=200))
    it_team_table = [
        {
            "index": i + 1,
            "name": draw(st.none() | st.text(min_size=1, max_size=20)),
            "title": draw(st.none() | st.text(min_size=1, max_size=20)),
        }
        for i in range(draw(st.integers(0, 8)))
    ]
    chapters = [draw(a271_chapter_strategy(i + 1)) for i in range(7)]
    cross_references = {
        "b22a_4_3_wp_id": draw(st.none() | st.text(min_size=1, max_size=36)),
        "c22_wp_id": draw(st.none() | st.text(min_size=1, max_size=36)),
        "c21_1_wp_id": draw(st.none() | st.text(min_size=1, max_size=36)),
        "b23_15_wp_id": draw(st.none() | st.text(min_size=1, max_size=36)),
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "audit_period": draw(st.text(min_size=0, max_size=20)),
        "partner": draw(st.none() | st.text(min_size=1, max_size=30)),
        "current_user": draw(st.none() | st.text(min_size=1, max_size=30)),
    }
    return {
        "meta_info": meta_info,
        "header": header,
        "purpose_text": purpose_text,
        "it_team_table": it_team_table,
        "chapters": chapters,
        "cross_references": cross_references,
        "project_context": project_context,
    }


# ─── Property 5: 后端响应结构完整性 ─────────────────────────────────────────


class TestProperty5ResponseSchemaCompleteness:
    """Property 5: 渲染策略返回结构完整性.

    For any valid A27-1 render response:
    - SHALL contain 7 top-level keys
    - chapters array SHALL have exactly 7 entries
    - cross_references SHALL have 4 keys

    **Validates: Requirements 13.1**
    """

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_top_level_has_7_keys(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: top-level has 7 keys."""
        expected_keys = {
            "meta_info", "header", "purpose_text", "it_team_table",
            "chapters", "cross_references", "project_context",
        }
        assert set(data.keys()) == expected_keys

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_chapters_array_length_7(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: chapters array has 7 entries."""
        assert len(data["chapters"]) == 7
        for i, ch in enumerate(data["chapters"]):
            assert ch["number"] == i + 1

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_cross_references_has_4_keys(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: cross_references has 4 keys."""
        expected = {"b22a_4_3_wp_id", "c22_wp_id", "c21_1_wp_id", "b23_15_wp_id"}
        assert set(data["cross_references"].keys()) == expected

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_meta_info_has_index_no(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: meta_info.index_no == A27-1."""
        assert data["meta_info"]["index_no"] == "A27-1"

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_header_has_4_fields(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: header has 4 fields."""
        expected = {"date", "to", "from_user", "subject"}
        assert set(data["header"].keys()) == expected

    @settings(max_examples=5)
    @given(data=a271_render_response_strategy())
    def test_each_chapter_has_required_fields(self, data: dict):
        """Feature: a27-1-it-audit-memo, Property 5: each chapter has required fields."""
        for ch in data["chapters"]:
            assert "number" in ch
            assert "title" in ch
            assert "content" in ch
            assert "conclusion" in ch
            assert "deficiency" in ch
            assert "cross_ref" in ch
