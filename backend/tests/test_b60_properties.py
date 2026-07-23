"""
Property-Based Tests for B60 Dedicated Component (backend).

Feature: b60-dedicated-component
Properties 1, 3, 4, 6, 7 — pure function tests (no DB, no async).
"""
import json
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st


# ─── B60 constants ──────────────────────────────────────────────────────────────

B60_SUB_WP_CODES = [
    "B60-1",
    "B60-2-1",
    "B60-2-2",
    "B60-2-3",
    "B60-3",
    "B60A",
    "B60B",
    "B60C",
    "B60D",
]

# ─── Pure functions under test ──────────────────────────────────────────────────


def build_wp_id_map(items: list[dict]) -> dict[str, str]:
    """
    Build wpIdMap from wp-index response array.

    Filters items whose wp_code starts with 'B60-' or exactly matches B60A~B60D.
    Maps wp_code → item.wp_id (NOT item.id).
    """
    result: dict[str, str] = {}
    for item in items:
        wp_code = item.get("wp_code", "")
        wp_id = item.get("wp_id", "")
        # Key matching: prefix 'B60-' or exact match B60A~B60D
        if wp_code.startswith("B60-") or wp_code in ("B60A", "B60B", "B60C", "B60D"):
            result[wp_code] = wp_id
    return result


def serialize_deserialize_applicability(
    mapping: dict[str, bool],
) -> dict[str, bool]:
    """
    Serialize applicability state to JSON, then deserialize back.
    Missing keys default to True.
    """
    # Serialize
    json_str = json.dumps(mapping)
    # Deserialize
    parsed = json.loads(json_str)
    # Rebuild with defaults for missing keys
    result: dict[str, bool] = {}
    for code in B60_SUB_WP_CODES:
        if code in parsed and isinstance(parsed[code], bool):
            result[code] = parsed[code]
        else:
            result[code] = True
    return result


def sort_chapters_by_id(chapters: list[dict]) -> list[dict]:
    """Sort chapter definitions by chapter_id (lexicographic order)."""
    return sorted(chapters, key=lambda c: c["chapter_id"])


def build_save_payload(chapter_id: str, content: str) -> dict:
    """
    Build the PUT payload item for saving chapter content.
    Returns dict with item_id=chapter_id, remark=content, conclusion=null.
    """
    return {
        "item_id": chapter_id,
        "remark": content,
        "conclusion": None,
    }


def sanitize_ai_context(context: dict[str, Any]) -> dict[str, str]:
    """
    Convert all context values to string type for AI generate-text call.
    None → empty string, numbers → str representation.
    """
    result: dict[str, str] = {}
    for key, value in context.items():
        if value is None:
            result[key] = ""
        else:
            result[key] = str(value)
    return result


# ─── Strategies ─────────────────────────────────────────────────────────────────

# Strategy for wp-index items with distinct id and wp_id fields
wp_index_item_strategy = st.fixed_dictionaries(
    {
        "id": st.uuids().map(str),
        "wp_id": st.uuids().map(str),
        "wp_code": st.sampled_from(
            [
                "B60",
                "B60-1",
                "B60-2-1",
                "B60-2-2",
                "B60-2-3",
                "B60-3",
                "B60A",
                "B60B",
                "B60C",
                "B60D",
                # Non-B60 items to test filtering
                "A11",
                "D2-1",
                "C24",
                "F1",
            ]
        ),
    }
)

# Strategy for applicability mapping (subset of B60 sub-wp codes)
applicability_strategy = st.fixed_dictionaries(
    {code: st.booleans() for code in B60_SUB_WP_CODES}
)

# Strategy for chapter definitions with shuffled order
chapter_id_strategy = st.lists(
    st.integers(min_value=1, max_value=30).map(lambda n: f"B60-CH-{n:02d}"),
    min_size=2,
    max_size=15,
    unique=True,
)

# Strategy for chapter_id
single_chapter_id_strategy = st.integers(min_value=1, max_value=99).map(
    lambda n: f"B60-CH-{n:02d}"
)

# Strategy for non-empty content text
content_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters="\n",
    ),
    min_size=1,
    max_size=500,
)

# Strategy for project context with mixed types (numbers, None, strings)
ai_context_strategy = st.fixed_dictionaries(
    {
        "client_name": st.one_of(st.text(min_size=1, max_size=50), st.none()),
        "audit_year": st.one_of(
            st.integers(min_value=2020, max_value=2030),
            st.text(min_size=4, max_size=4),
            st.none(),
        ),
        "business_category": st.one_of(st.text(min_size=1, max_size=30), st.none()),
        "chapter_title": st.one_of(st.text(min_size=1, max_size=100), st.none()),
    }
)


# ─── Property Tests ─────────────────────────────────────────────────────────────


@settings(max_examples=5)
@given(items=st.lists(wp_index_item_strategy, min_size=1, max_size=20))
def test_property_1_wp_id_map_uses_wp_id(items: list[dict]):
    """
    Feature: b60-dedicated-component, Property 1: wpIdMap 构建使用 wp_id 字段

    For any wp-index response array containing id and wp_id as different fields,
    wpIdMap values must come from item.wp_id (not item.id), and key matching rule
    is wp_code prefix 'B60-' or exact match B60A~B60D.

    **Validates: Requirements 1.4**
    """
    wp_id_map = build_wp_id_map(items)

    # Build expected: last-write-wins for duplicate wp_codes (dict semantics)
    expected_b60_codes: set[str] = set()
    last_wp_id_for_code: dict[str, str] = {}
    last_id_for_code: dict[str, str] = {}

    for item in items:
        wp_code = item["wp_code"]
        is_b60 = wp_code.startswith("B60-") or wp_code in (
            "B60A",
            "B60B",
            "B60C",
            "B60D",
        )
        if is_b60:
            expected_b60_codes.add(wp_code)
            last_wp_id_for_code[wp_code] = item["wp_id"]
            last_id_for_code[wp_code] = item["id"]

    # Property: map keys == exactly B60 codes found in items
    assert set(wp_id_map.keys()) == expected_b60_codes

    # Property: each map value equals wp_id of last item (NOT item.id)
    for wp_code in expected_b60_codes:
        assert wp_id_map[wp_code] == last_wp_id_for_code[wp_code]
        # Ensure it's the wp_id field, not the id field
        if last_id_for_code[wp_code] != last_wp_id_for_code[wp_code]:
            assert wp_id_map[wp_code] != last_id_for_code[wp_code]

    # Non-B60 items must NOT be in map
    non_b60_codes = {
        item["wp_code"]
        for item in items
        if not (
            item["wp_code"].startswith("B60-")
            or item["wp_code"] in ("B60A", "B60B", "B60C", "B60D")
        )
    }
    for code in non_b60_codes:
        assert code not in wp_id_map


@settings(max_examples=5)
@given(mapping=applicability_strategy)
def test_property_3_applicability_json_roundtrip(mapping: dict[str, bool]):
    """
    Feature: b60-dedicated-component, Property 3: 适用性 JSON 往返

    For any applicability state Record<string, boolean> (8 B60 series sub-workpaper
    codes as keys), serializing to JSON then deserializing should produce an equal
    mapping. Missing keys default to true.

    **Validates: Requirements 3.2, 3.3, 3.4**
    """
    result = serialize_deserialize_applicability(mapping)

    # All 8 keys must be present
    assert set(result.keys()) == set(B60_SUB_WP_CODES)

    # Values must match original (all keys provided in this test)
    for code in B60_SUB_WP_CODES:
        assert result[code] == mapping[code]


@settings(max_examples=5)
@given(chapter_ids=chapter_id_strategy)
def test_property_4_chapter_sort_invariant(chapter_ids: list[str]):
    """
    Feature: b60-dedicated-component, Property 4: 章节排序不变量

    For any chapter definitions array, the rendered order must satisfy
    chapters[i].chapter_id < chapters[i+1].chapter_id (lexicographic order).

    **Validates: Requirements 4.4**
    """
    # Build shuffled chapter list
    import random

    chapters = [{"chapter_id": cid, "title": f"Chapter {cid}"} for cid in chapter_ids]
    random.shuffle(chapters)

    # Sort
    sorted_chapters = sort_chapters_by_id(chapters)

    # Verify lexicographic order
    for i in range(len(sorted_chapters) - 1):
        assert sorted_chapters[i]["chapter_id"] < sorted_chapters[i + 1]["chapter_id"]


@settings(max_examples=5)
@given(chapter_id=single_chapter_id_strategy, content=content_strategy)
def test_property_6_chapter_content_persistence_roundtrip(
    chapter_id: str, content: str
):
    """
    Feature: b60-dedicated-component, Property 6: 章节内容持久化往返

    For any chapter_id and non-empty content text, the saved PUT payload must have
    item_id=chapter_id, remark=content, conclusion=null.

    **Validates: Requirements 6.1, 6.2**
    """
    payload = build_save_payload(chapter_id, content)

    assert payload["item_id"] == chapter_id
    assert payload["remark"] == content
    assert payload["conclusion"] is None


@settings(max_examples=5)
@given(context=ai_context_strategy)
def test_property_7_ai_context_type_safety(context: dict[str, Any]):
    """
    Feature: b60-dedicated-component, Property 7: AI context 类型安全

    For any project context containing numbers/None, when converted for the AI
    generate-text call, all context values must be string type (no number/null/undefined).

    **Validates: Requirements 7.2**
    """
    sanitized = sanitize_ai_context(context)

    # All values must be strings
    for key, value in sanitized.items():
        assert isinstance(value, str), (
            f"context[{key!r}] = {value!r} is {type(value).__name__}, expected str"
        )

    # All original keys must be preserved
    assert set(sanitized.keys()) == set(context.keys())
