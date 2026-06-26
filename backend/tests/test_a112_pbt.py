"""Property-Based Tests for A1-12 checklist parser using hypothesis.

Property 7: 解析输出结构完整性
Property 8: Round-Trip 等价 (parse → format_to_docx → re-parse)

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 7.1, 7.2**
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.a112_checklist_parser import format_to_docx, parse_a112_checklist

# ─── 模板路径 ────────────────────────────────────────────────────────────────

_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "wp_templates"
    / "A"
    / "A1-12 重大事项决定程序的履行情况核查表1105.docx"
)


# ─── Property 7: 解析输出结构完整性 ──────────────────────────────────────────


class TestProperty7ParseOutputStructuralIntegrity:
    """Property 7: 解析输出结构完整性.

    For the real A1-12 DOCX template: parsing should produce exactly 2 categories,
    category[0] has 14 items, all items have unique IDs, all items have non-empty description.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """

    @settings(max_examples=5)
    @given(st.integers(min_value=0, max_value=100))
    def test_parse_produces_exactly_2_categories(self, _seed: int):
        """Property 7a: 解析固定模板始终产生恰好 2 个 categories."""
        result = parse_a112_checklist(str(_TEMPLATE))
        assert len(result["categories"]) == 2, (
            f"Expected 2 categories, got {len(result['categories'])}"
        )

    @settings(max_examples=5)
    @given(st.integers(min_value=0, max_value=100))
    def test_category_0_has_14_items(self, _seed: int):
        """Property 7b: 第一类恒定有 14 项固定条目."""
        result = parse_a112_checklist(str(_TEMPLATE))
        cat0 = result["categories"][0]
        assert len(cat0["items"]) == 14, (
            f"Expected 14 items in category[0], got {len(cat0['items'])}"
        )

    @settings(max_examples=5)
    @given(st.integers(min_value=0, max_value=100))
    def test_all_item_ids_unique(self, _seed: int):
        """Property 7c: 所有 item ID 全局唯一."""
        result = parse_a112_checklist(str(_TEMPLATE))
        all_ids = [
            item["id"]
            for cat in result["categories"]
            for item in cat["items"]
        ]
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate IDs found: {[x for x in all_ids if all_ids.count(x) > 1]}"
        )

    @settings(max_examples=5)
    @given(st.integers(min_value=0, max_value=100))
    def test_all_items_have_nonempty_description(self, _seed: int):
        """Property 7d: 所有 item 的 description 非空."""
        result = parse_a112_checklist(str(_TEMPLATE))
        for cat in result["categories"]:
            for item in cat["items"]:
                assert item["description"].strip(), (
                    f"{item['id']} has empty description"
                )


# ─── Hypothesis Strategies for A112ChecklistData ─────────────────────────────


# XML-safe text strategy: only printable characters compatible with DOCX/XML
_xml_safe_text_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
        "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
    ),
    min_size=2,
    max_size=20,
)

# Chinese text strategy for descriptions (safe for XML)
_cn_desc_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="，。、；",
    ),
    min_size=3,
    max_size=40,
)


# Full A112ChecklistData strategy
@st.composite
def a112_checklist_data_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid A112ChecklistData dict for round-trip testing."""
    # header — use XML-safe text only
    header = draw(st.fixed_dictionaries({
        "entity_name": st.one_of(st.none(), _xml_safe_text_st),
        "period_end": st.one_of(st.none(), st.from_regex(r"20\d{2}年\d{1,2}月\d{1,2}日", fullmatch=True)),
        "business_class": st.just(None),
        "is_first_engagement": st.just(None),
    }))

    # 1-3 categories, each with 1-14 items
    num_categories = draw(st.integers(min_value=1, max_value=3))
    categories = []
    global_seq = 0
    for cat_idx in range(1, num_categories + 1):
        num_items = draw(st.integers(min_value=1, max_value=14))
        prefixes = ["一", "二", "三"]
        prefix = prefixes[cat_idx - 1] if cat_idx <= 3 else f"第{cat_idx}"
        cat_tag_prefix = chr(ord("A") + cat_idx - 1)

        items = []
        for i in range(num_items):
            global_seq += 1
            desc = draw(_cn_desc_st)
            tag = f"{cat_tag_prefix}{i + 1}"
            items.append({
                "id": f"item-{global_seq}",
                "seq": global_seq,
                "description": f"{desc}({tag})",
                "category_tag": tag,
            })

        categories.append({
            "id": f"cat-{cat_idx}",
            "title": f"{prefix}、测试类别{cat_idx}",
            "items": items,
            "allow_custom": cat_idx >= 2,
        })

    # 4 signatures
    signatures = [
        {"role": "项目负责经理", "name": None, "date": None},
        {"role": "项目合伙人", "name": None, "date": None},
        {"role": "质量复核合伙人", "name": None, "date": None},
        {"role": "质量控制复核人", "name": None, "date": None},
    ]

    return {
        "header": header,
        "categories": categories,
        "signatures": signatures,
    }


# ─── Property 8: Round-Trip 等价 ─────────────────────────────────────────────


class TestProperty8RoundTripEquivalence:
    """Property 8: Round-Trip 等价.

    parse_a112_checklist → format_to_docx → re-parse should produce equivalent data.
    Verify: same category count, same category titles, same items per category,
    same descriptions, same category_tags.

    **Validates: Requirements 7.1, 7.2**
    """

    @settings(max_examples=5)
    @given(data=a112_checklist_data_strategy())
    def test_roundtrip_preserves_category_count(self, data: dict):
        """Round-trip 保持 category 数量不变."""
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert len(reparsed["categories"]) == len(data["categories"]), (
            f"Category count mismatch: original={len(data['categories'])}, "
            f"reparsed={len(reparsed['categories'])}"
        )

    @settings(max_examples=5)
    @given(data=a112_checklist_data_strategy())
    def test_roundtrip_preserves_category_titles(self, data: dict):
        """Round-trip 保持 category titles 不变."""
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        for i, (orig_cat, re_cat) in enumerate(
            zip(data["categories"], reparsed["categories"])
        ):
            assert re_cat["title"] == orig_cat["title"], (
                f"Category {i} title mismatch: "
                f"original='{orig_cat['title']}', reparsed='{re_cat['title']}'"
            )

    @settings(max_examples=5)
    @given(data=a112_checklist_data_strategy())
    def test_roundtrip_preserves_items_per_category(self, data: dict):
        """Round-trip 保持每个 category 的 item 数量不变."""
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        for i, (orig_cat, re_cat) in enumerate(
            zip(data["categories"], reparsed["categories"])
        ):
            assert len(re_cat["items"]) == len(orig_cat["items"]), (
                f"Category {i} items count mismatch: "
                f"original={len(orig_cat['items'])}, reparsed={len(re_cat['items'])}"
            )

    @settings(max_examples=5)
    @given(data=a112_checklist_data_strategy())
    def test_roundtrip_preserves_descriptions(self, data: dict):
        """Round-trip 保持所有 item descriptions 不变."""
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        for ci, (orig_cat, re_cat) in enumerate(
            zip(data["categories"], reparsed["categories"])
        ):
            for ii, (orig_item, re_item) in enumerate(
                zip(orig_cat["items"], re_cat["items"])
            ):
                assert re_item["description"] == orig_item["description"], (
                    f"Cat {ci} Item {ii} description mismatch: "
                    f"original='{orig_item['description']}', "
                    f"reparsed='{re_item['description']}'"
                )

    @settings(max_examples=5)
    @given(data=a112_checklist_data_strategy())
    def test_roundtrip_preserves_category_tags(self, data: dict):
        """Round-trip 保持所有 item category_tags 不变."""
        buf = format_to_docx(data)

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(buf.read())
            tmp_path = f.name

        try:
            reparsed = parse_a112_checklist(tmp_path)
        finally:
            os.unlink(tmp_path)

        for ci, (orig_cat, re_cat) in enumerate(
            zip(data["categories"], reparsed["categories"])
        ):
            for ii, (orig_item, re_item) in enumerate(
                zip(orig_cat["items"], re_cat["items"])
            ):
                assert re_item["category_tag"] == orig_item["category_tag"], (
                    f"Cat {ci} Item {ii} category_tag mismatch: "
                    f"original='{orig_item['category_tag']}', "
                    f"reparsed='{re_item['category_tag']}'"
                )
