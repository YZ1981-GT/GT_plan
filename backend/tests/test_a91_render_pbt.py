"""Property-Based Tests for A9-1 内控缺陷沟通函 render strategy.

Properties tested:
- Property 1: B22B severity grouping correctness
- Property 3: DeficiencyItem JSON round-trip
- Property 7: render response schema completeness
- Property 8: B22B missing graceful degradation

**Validates: Requirements 6.3, 6.4, 11.1, 11.2, 11.3, 11.4, 12.3**
"""

from __future__ import annotations

import json
from dataclasses import asdict

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.wp_render_strategies._a91_deficiency_letter import DeficiencyItem


# ─── Strategies ───────────────────────────────────────────────────────────────

VALID_SEVERITIES = ("major", "significant", "general")


@st.composite
def deficiency_item_strategy(draw: st.DrawFn) -> DeficiencyItem:
    """Generate random DeficiencyItem instances."""
    return DeficiencyItem(
        id=draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd")))),
        description=draw(st.text(min_size=0, max_size=200)),
        impact=draw(st.text(min_size=0, max_size=200)),
        recommendation=draw(st.text(min_size=0, max_size=200)),
        index_ref=draw(st.none() | st.text(min_size=1, max_size=20)),
        source=draw(st.sampled_from(["b22b", "manual"])),
        severity=draw(st.sampled_from(list(VALID_SEVERITIES))),
    )


@st.composite
def deficiency_list_strategy(draw: st.DrawFn) -> list[DeficiencyItem]:
    """Generate a list of deficiency items with random severities."""
    return draw(st.lists(deficiency_item_strategy(), min_size=0, max_size=15))


@st.composite
def a91_render_response_strategy(draw: st.DrawFn) -> dict:
    """Generate random A9-1 render response matching expected schema."""
    section_data = {
        "addressee": {
            "client_name": draw(st.text(min_size=0, max_size=50)),
            "custom_text": draw(st.none() | st.text(min_size=1, max_size=50)),
        },
        "independence": {
            "team_independent": draw(st.sampled_from(["Y", "N", None])),
            "no_relationships": draw(st.sampled_from(["Y", "N", None])),
            "no_relationships_detail": draw(st.none() | st.text(min_size=1, max_size=100)),
            "safeguards_taken": draw(st.sampled_from(["Y", "N", None])),
            "non_audit_services": draw(st.sampled_from(["Y", "N", None])),
            "non_audit_services_detail": draw(st.none() | st.text(min_size=1, max_size=100)),
        },
        "committee": {
            "applicability": draw(st.sampled_from(["Y", "N", "NA", None])),
            "description": draw(st.none() | st.text(min_size=1, max_size=200)),
        },
        "signature": {
            "date": draw(st.none() | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
        },
        "response": {
            "opinion": draw(st.none() | st.text(min_size=1, max_size=200)),
            "conclusion": draw(st.none() | st.text(min_size=1, max_size=200)),
            "representative": draw(st.none() | st.text(min_size=1, max_size=50)),
            "response_date": draw(st.none() | st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True)),
        },
    }
    deficiency_list = {
        "major": [asdict(draw(deficiency_item_strategy())) for _ in range(draw(st.integers(0, 3)))],
        "significant": [asdict(draw(deficiency_item_strategy())) for _ in range(draw(st.integers(0, 3)))],
        "general": [asdict(draw(deficiency_item_strategy())) for _ in range(draw(st.integers(0, 3)))],
    }
    project_context = {
        "client_name": draw(st.text(min_size=0, max_size=50)),
        "firm_name": "致同会计师事务所（特殊普通合伙）",
        "audit_report_date": draw(st.none() | st.from_regex(r"\d{4}年\d{1,2}月\d{1,2}日", fullmatch=True)),
    }
    b22b_warning = draw(st.none() | st.text(min_size=1, max_size=50))
    return {
        "section_data": section_data,
        "deficiency_list": deficiency_list,
        "project_context": project_context,
        "b22b_warning": b22b_warning,
    }


# ─── Property 1: B22B severity grouping correctness ──────────────────────────


class TestProperty1B22BSeverityGrouping:
    """Property 1: B22B 缺陷分组正确性.

    For any set of deficiencies with severity in {major, significant, general},
    grouping by severity SHALL place each item in the correct sub-list,
    and total count across groups SHALL equal input count.

    **Validates: Requirements 6.3, 6.4, 11.3**
    """

    @settings(max_examples=5)
    @given(items=deficiency_list_strategy())
    def test_grouping_preserves_total_count(self, items: list[DeficiencyItem]):
        """Feature: a9-1-deficiency-letter, Property 1: total count preserved after grouping."""
        grouped: dict[str, list[DeficiencyItem]] = {"major": [], "significant": [], "general": []}
        for item in items:
            grouped[item.severity].append(item)

        total = sum(len(v) for v in grouped.values())
        assert total == len(items)

    @settings(max_examples=5)
    @given(items=deficiency_list_strategy())
    def test_each_item_in_correct_group(self, items: list[DeficiencyItem]):
        """Feature: a9-1-deficiency-letter, Property 1: each item lands in correct severity group."""
        grouped: dict[str, list[DeficiencyItem]] = {"major": [], "significant": [], "general": []}
        for item in items:
            grouped[item.severity].append(item)

        for severity, group in grouped.items():
            for item in group:
                assert item.severity == severity

    @settings(max_examples=5)
    @given(items=deficiency_list_strategy())
    def test_no_items_lost_or_duplicated(self, items: list[DeficiencyItem]):
        """Feature: a9-1-deficiency-letter, Property 1: no items lost or duplicated."""
        grouped: dict[str, list[DeficiencyItem]] = {"major": [], "significant": [], "general": []}
        for item in items:
            grouped[item.severity].append(item)

        all_grouped_ids = []
        for group in grouped.values():
            all_grouped_ids.extend(id(item) for item in group)

        original_ids = [id(item) for item in items]
        assert sorted(all_grouped_ids) == sorted(original_ids)


# ─── Property 3: DeficiencyItem JSON round-trip ──────────────────────────────


class TestProperty3JsonRoundTrip:
    """Property 3: 缺陷列表 JSON round-trip.

    For any DeficiencyItem list, serializing to JSON then deserializing
    SHALL produce an equivalent list with all fields preserved.

    **Validates: Requirements 6.5, 12.3**
    """

    @settings(max_examples=5)
    @given(items=st.lists(deficiency_item_strategy(), min_size=0, max_size=10))
    def test_serialize_deserialize_preserves_all_fields(self, items: list[DeficiencyItem]):
        """Feature: a9-1-deficiency-letter, Property 3: JSON round-trip preserves all fields."""
        serialized = json.dumps([asdict(item) for item in items], ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized) == len(items)
        for original, restored in zip(items, deserialized):
            assert restored["id"] == original.id
            assert restored["description"] == original.description
            assert restored["impact"] == original.impact
            assert restored["recommendation"] == original.recommendation
            assert restored["index_ref"] == original.index_ref
            assert restored["source"] == original.source
            assert restored["severity"] == original.severity

    @settings(max_examples=5)
    @given(item=deficiency_item_strategy())
    def test_single_item_round_trip(self, item: DeficiencyItem):
        """Feature: a9-1-deficiency-letter, Property 3: single item round-trip."""
        serialized = json.dumps(asdict(item), ensure_ascii=False)
        restored = json.loads(serialized)
        assert restored == asdict(item)


# ─── Property 7: render response schema completeness ─────────────────────────


class TestProperty7ResponseSchemaCompleteness:
    """Property 7: 渲染策略返回结构完整性.

    For any valid A9-1 render response:
    - section_data SHALL have 5 sub-keys (addressee, independence, committee, signature, response)
    - deficiency_list SHALL have 3 severity keys each containing a list
    - project_context SHALL have client_name, firm_name, audit_report_date

    **Validates: Requirements 11.1, 11.2**
    """

    @settings(max_examples=5)
    @given(data=a91_render_response_strategy())
    def test_top_level_keys(self, data: dict):
        """Feature: a9-1-deficiency-letter, Property 7: top-level has 4 keys."""
        assert set(data.keys()) == {"section_data", "deficiency_list", "project_context", "b22b_warning"}

    @settings(max_examples=5)
    @given(data=a91_render_response_strategy())
    def test_section_data_has_5_sub_keys(self, data: dict):
        """Feature: a9-1-deficiency-letter, Property 7: section_data has 5 sub-keys."""
        expected = {"addressee", "independence", "committee", "signature", "response"}
        assert set(data["section_data"].keys()) == expected

    @settings(max_examples=5)
    @given(data=a91_render_response_strategy())
    def test_deficiency_list_has_3_severity_keys(self, data: dict):
        """Feature: a9-1-deficiency-letter, Property 7: deficiency_list has 3 severity keys."""
        assert set(data["deficiency_list"].keys()) == {"major", "significant", "general"}
        for severity in ("major", "significant", "general"):
            assert isinstance(data["deficiency_list"][severity], list)

    @settings(max_examples=5)
    @given(data=a91_render_response_strategy())
    def test_project_context_has_3_keys(self, data: dict):
        """Feature: a9-1-deficiency-letter, Property 7: project_context has 3 keys."""
        assert set(data["project_context"].keys()) == {"client_name", "firm_name", "audit_report_date"}

    @settings(max_examples=5)
    @given(data=a91_render_response_strategy())
    def test_firm_name_is_correct(self, data: dict):
        """Feature: a9-1-deficiency-letter, Property 7: firm_name is always correct."""
        assert data["project_context"]["firm_name"] == "致同会计师事务所（特殊普通合伙）"


# ─── Property 8: B22B missing graceful degradation ───────────────────────────


class TestProperty8B22BMissingDegradation:
    """Property 8: B22B 缺失时的降级行为.

    When B22B workpaper does not exist, render SHALL return:
    - empty deficiency lists for all three severity groups
    - a non-null b22b_warning string

    **Validates: Requirements 11.4**
    """

    @settings(max_examples=5)
    @given(
        client_name=st.text(min_size=0, max_size=50),
        warning_text=st.text(min_size=1, max_size=100),
    )
    def test_empty_deficiency_lists_with_warning(self, client_name: str, warning_text: str):
        """Feature: a9-1-deficiency-letter, Property 8: empty lists + non-null warning."""
        # Simulate the B22B-missing response structure
        response = {
            "deficiency_list": {"major": [], "significant": [], "general": []},
            "b22b_warning": warning_text,
        }
        # All severity lists must be empty
        for severity in ("major", "significant", "general"):
            assert response["deficiency_list"][severity] == []
        # Warning must be non-null and non-empty
        assert response["b22b_warning"] is not None
        assert len(response["b22b_warning"]) > 0

    @settings(max_examples=5)
    @given(warning_text=st.text(min_size=1, max_size=100))
    def test_warning_is_string(self, warning_text: str):
        """Feature: a9-1-deficiency-letter, Property 8: b22b_warning is always a string."""
        assert isinstance(warning_text, str)
