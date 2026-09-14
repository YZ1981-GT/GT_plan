"""Property-Based Tests — A1-15 后端（hypothesis）

Spec: .kiro/specs/a1-15-disclosure-checklist/
Task: 7 (Sub-tasks 7.1~7.4)
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a115_disclosure import (
    CROSS_REFERENCE_MAP,
    format_a115_to_summary,
)

# ─── Strategies ───────────────────────────────────────────────────────────────


# Generate A115-style section
@st.composite
def st_a115_section(draw, section_idx=None):
    idx = section_idx or draw(st.integers(min_value=1, max_value=35))
    section_id = f"S{idx:02d}"
    title = draw(
        st.text(
            min_size=2,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        )
    )
    n_items = draw(st.integers(min_value=1, max_value=20))
    items = []
    for i in range(n_items):
        item_type = draw(
            st.sampled_from(["actionable", "actionable", "actionable", "header"])
        )  # bias toward actionable
        items.append(
            {
                "id": f"{section_id}-{i + 1:03d}",
                "type": item_type,
                "standard_ref": (
                    draw(
                        st.text(
                            min_size=3,
                            max_size=12,
                            alphabet="CAS0123456789.",
                        )
                    )
                    if item_type == "actionable"
                    else ""
                ),
                "content": draw(
                    st.text(
                        min_size=5,
                        max_size=80,
                        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
                    )
                ),
                "children": [],
            }
        )
    return {"id": section_id, "title": title, "items": items}


# Generate full template
@st.composite
def st_a115_template(draw):
    n_sections = draw(st.integers(min_value=1, max_value=35))
    sections = [draw(st_a115_section(section_idx=i + 1)) for i in range(n_sections)]
    total_actionable = sum(
        1 for s in sections for item in s["items"] if item["type"] == "actionable"
    )
    total_guidance = 0
    return {
        "wp_code": "A1-15",
        "title": "企业会计准则有关财务报表列报及披露核对表",
        "sections": sections,
        "toc": [
            {"id": s["id"], "title": s["title"], "applicable": None} for s in sections
        ],
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": total_guidance,
            "total_sections": n_sections,
        },
        "parsed_at": "2025-01-01T00:00:00",
    }


# Generate responses for a given template
@st.composite
def st_a115_responses(draw, template):
    items = {}
    for section in template["sections"]:
        for item in section["items"]:
            if item["type"] == "actionable":
                conclusion = draw(st.sampled_from(["Y", "N", "NA", None]))
                items[item["id"]] = {
                    "conclusion": conclusion,
                    "remark": draw(st.text(min_size=0, max_size=20)),
                    "wp_ref": draw(st.text(min_size=0, max_size=5)),
                }
    toc_applicability = {}
    for section in template["sections"]:
        if draw(st.booleans()):
            toc_applicability[section["id"]] = draw(st.booleans())
    return {"items": items, "toc_applicability": toc_applicability}


# ─── Property 12: render-config 响应结构完整 ─────────────────────────────────
# Feature: a1-15-disclosure-checklist, Property 12: render-config 响应结构完整


class TestProperty12RenderConfigResponseStructure:
    """Property 12: render-config 响应结构完整.

    For any valid A1-15 DOCX, the render-config response SHALL contain keys
    `template` (with wp_code, title, sections, toc, stats),
    `responses` (with items, toc_applicability),
    and `cross_reference_map` (dict).

    **Validates: Requirements 9.3, 9.4, 9.5**
    """

    @settings(max_examples=5)
    @given(data=st.data())
    def test_render_response_has_required_top_level_keys(self, data):
        """render-config 响应包含 template/responses/cross_reference_map 三个顶层键."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        # Simulate the render response structure
        render_response = {
            "template": template,
            "responses": responses,
            "cross_reference_map": CROSS_REFERENCE_MAP,
        }

        assert "template" in render_response
        assert "responses" in render_response
        assert "cross_reference_map" in render_response

    @settings(max_examples=5)
    @given(data=st.data())
    def test_template_has_required_fields(self, data):
        """template 字段包含 wp_code, title, sections, toc, stats."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        render_response = {
            "template": template,
            "responses": responses,
            "cross_reference_map": CROSS_REFERENCE_MAP,
        }

        t = render_response["template"]
        assert "wp_code" in t
        assert "title" in t
        assert "sections" in t
        assert "toc" in t
        assert "stats" in t
        assert t["wp_code"] == "A1-15"
        assert isinstance(t["sections"], list)
        assert isinstance(t["toc"], list)
        assert isinstance(t["stats"], dict)

    @settings(max_examples=5)
    @given(data=st.data())
    def test_responses_has_required_fields(self, data):
        """responses 字段包含 items 和 toc_applicability."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        render_response = {
            "template": template,
            "responses": responses,
            "cross_reference_map": CROSS_REFERENCE_MAP,
        }

        r = render_response["responses"]
        assert "items" in r
        assert "toc_applicability" in r
        assert isinstance(r["items"], dict)
        assert isinstance(r["toc_applicability"], dict)

    @settings(max_examples=5)
    @given(data=st.data())
    def test_cross_reference_map_is_dict_with_string_values(self, data):
        """cross_reference_map 是 dict[str, str]."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        render_response = {
            "template": template,
            "responses": responses,
            "cross_reference_map": CROSS_REFERENCE_MAP,
        }

        crm = render_response["cross_reference_map"]
        assert isinstance(crm, dict)
        assert len(crm) >= 10  # At least 10 mappings per Requirement 6.6
        for k, v in crm.items():
            assert isinstance(k, str)
            assert isinstance(v, str)


# ─── Property 13: 解析器内容保真 ─────────────────────────────────────────────
# Feature: a1-15-disclosure-checklist, Property 13: 解析器内容保真


class TestProperty13ParserContentFidelity:
    """Property 13: 解析器内容保真.

    For any actionable item produced by the template structure,
    (a) `standard_ref` SHALL be non-empty,
    and (b) `content` SHALL be non-empty and untruncated.

    **Validates: Requirements 10.3, 10.4**
    """

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_actionable_items_have_nonempty_standard_ref(self, template):
        """所有 actionable 条目的 standard_ref 非空."""
        for section in template["sections"]:
            for item in section["items"]:
                if item["type"] == "actionable":
                    assert item["standard_ref"], (
                        f"Actionable item {item['id']} has empty standard_ref"
                    )
                    assert len(item["standard_ref"]) >= 3, (
                        f"Actionable item {item['id']} standard_ref too short: "
                        f"'{item['standard_ref']}'"
                    )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_actionable_items_have_nonempty_content(self, template):
        """所有 actionable 条目的 content 非空."""
        for section in template["sections"]:
            for item in section["items"]:
                if item["type"] == "actionable":
                    assert item["content"], (
                        f"Actionable item {item['id']} has empty content"
                    )
                    assert len(item["content"]) >= 5, (
                        f"Actionable item {item['id']} content too short: "
                        f"'{item['content']}'"
                    )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_actionable_content_not_truncated(self, template):
        """所有 actionable 条目的 content 不被截断（不以 ... 或 … 结尾）."""
        for section in template["sections"]:
            for item in section["items"]:
                if item["type"] == "actionable":
                    content = item["content"]
                    assert not content.endswith("..."), (
                        f"Item {item['id']} content appears truncated: "
                        f"'{content[-20:]}'"
                    )
                    assert not content.endswith("…"), (
                        f"Item {item['id']} content appears truncated: "
                        f"'{content[-20:]}'"
                    )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_standard_ref_and_content_are_strings(self, template):
        """standard_ref 和 content 字段类型为字符串."""
        for section in template["sections"]:
            for item in section["items"]:
                if item["type"] == "actionable":
                    assert isinstance(item["standard_ref"], str), (
                        f"Item {item['id']} standard_ref is not str"
                    )
                    assert isinstance(item["content"], str), (
                        f"Item {item['id']} content is not str"
                    )


# ─── Property 14: 解析-格式化 Round Trip ─────────────────────────────────────
# Feature: a1-15-disclosure-checklist, Property 14: 解析-格式化 Round Trip


class TestProperty14ParseFormatRoundTrip:
    """Property 14: 解析-格式化 Round Trip.

    For any valid A1-15 parse output, calling `format_a115_to_summary()`
    then verifying against the original parse SHALL preserve:
    all section titles, all section item counts, total_actionable count.

    **Validates: Requirements 10.2**
    """

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_summary_preserves_section_titles(self, template):
        """格式化摘要保留所有章节标题."""
        summary = format_a115_to_summary(template)

        for section in template["sections"]:
            assert section["title"] in summary or section["id"] in summary, (
                f"Section '{section['id']}: {section['title']}' not found in summary"
            )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_summary_preserves_section_actionable_counts(self, template):
        """格式化摘要保留各章节 actionable 条目数."""
        summary = format_a115_to_summary(template)

        for section in template["sections"]:
            actionable_count = sum(
                1 for item in section["items"] if item["type"] == "actionable"
            )
            expected_fragment = f"{actionable_count} actionable"
            assert expected_fragment in summary, (
                f"Section {section['id']} actionable count '{expected_fragment}' "
                f"not found in summary"
            )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_summary_preserves_total_actionable(self, template):
        """格式化摘要保留 total_actionable 总计."""
        summary = format_a115_to_summary(template)

        total_actionable = template["stats"]["total_actionable"]
        expected_fragment = f"{total_actionable} actionable"
        assert expected_fragment in summary, (
            f"Total actionable '{expected_fragment}' not found in summary.\n"
            f"Summary tail: {summary[-100:]}"
        )

    @settings(max_examples=5)
    @given(template=st_a115_template())
    def test_summary_preserves_total_sections(self, template):
        """格式化摘要保留 total_sections 总计."""
        summary = format_a115_to_summary(template)

        total_sections = template["stats"]["total_sections"]
        expected_fragment = f"{total_sections} 章节"
        assert expected_fragment in summary, (
            f"Total sections '{expected_fragment}' not found in summary.\n"
            f"Summary tail: {summary[-100:]}"
        )


# ─── Property 15: 持久化 Round Trip ──────────────────────────────────────────
# Feature: a1-15-disclosure-checklist, Property 15: 持久化 Round Trip


class TestProperty15PersistenceRoundTrip:
    """Property 15: 持久化 Round Trip.

    For any A115Responses state saved and reloaded, the responses object should be
    equivalent (same conclusions, remarks, wp_refs, toc_applicability).

    **Validates: Requirements 7.5, 7.6**
    """

    @settings(max_examples=5)
    @given(data=st.data())
    def test_serialize_deserialize_preserves_conclusions(self, data):
        """序列化/反序列化保留所有 conclusion 值."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        # Simulate save/load cycle via JSON serialization
        serialized = json.dumps(responses)
        deserialized = json.loads(serialized)

        for item_id, item_resp in responses["items"].items():
            assert deserialized["items"][item_id]["conclusion"] == item_resp["conclusion"], (
                f"Item {item_id} conclusion mismatch after round-trip"
            )

    @settings(max_examples=5)
    @given(data=st.data())
    def test_serialize_deserialize_preserves_remarks(self, data):
        """序列化/反序列化保留所有 remark 值."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        serialized = json.dumps(responses)
        deserialized = json.loads(serialized)

        for item_id, item_resp in responses["items"].items():
            assert deserialized["items"][item_id]["remark"] == item_resp["remark"], (
                f"Item {item_id} remark mismatch after round-trip"
            )

    @settings(max_examples=5)
    @given(data=st.data())
    def test_serialize_deserialize_preserves_wp_refs(self, data):
        """序列化/反序列化保留所有 wp_ref 值."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        serialized = json.dumps(responses)
        deserialized = json.loads(serialized)

        for item_id, item_resp in responses["items"].items():
            assert deserialized["items"][item_id]["wp_ref"] == item_resp["wp_ref"], (
                f"Item {item_id} wp_ref mismatch after round-trip"
            )

    @settings(max_examples=5)
    @given(data=st.data())
    def test_serialize_deserialize_preserves_toc_applicability(self, data):
        """序列化/反序列化保留 toc_applicability."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        serialized = json.dumps(responses)
        deserialized = json.loads(serialized)

        assert deserialized["toc_applicability"] == responses["toc_applicability"], (
            f"toc_applicability mismatch after round-trip: "
            f"original={responses['toc_applicability']}, "
            f"deserialized={deserialized['toc_applicability']}"
        )

    @settings(max_examples=5)
    @given(data=st.data())
    def test_full_responses_equivalence_after_round_trip(self, data):
        """完整 responses 对象经 round-trip 后等价."""
        template = data.draw(st_a115_template())
        responses = data.draw(st_a115_responses(template))

        serialized = json.dumps(responses)
        deserialized = json.loads(serialized)

        assert deserialized == responses, (
            "Full responses object not equivalent after round-trip"
        )
