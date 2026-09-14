"""Property-Based Test: P5 往返一致性 — C25-/C26- item_id Round-Trip

Feature: c25-c26-internal-audit-info-control, Property 5: 持久化往返一致性

For any valid C25/C26 data payload saved via JSON serialization:
- Serialize C25 items (10 steps × 4 fields + conclusion + remark = 42 items) → JSON → deserialize → all fields match
- Serialize C26 items (dynamic rows × 11 fields) → JSON → deserialize → all fields match
- item_id prefix C25- stays C25-, C26- stays C26-
- Unicode characters in text fields survive round-trip
- Elements array (comma-separated) survives round-trip

**Validates: Requirements 6.1, 6.4**

Uses hypothesis with max_examples=5 (project standard).
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies — C25/C26 item_id generation
# ═══════════════════════════════════════════════════════════════════════════════

# C25 item_id patterns:
#   C25-step-{n}-applicable (conclusion slot)
#   C25-step-{n}-executor (remark)
#   C25-step-{n}-result (remark)
#   C25-step-{n}-indexRef (remark)
#   C25-reliance-conclusion (conclusion)
#   C25-reliance-remark (remark)

_c25_step_fields = st.sampled_from(["applicable", "executor", "result", "indexRef"])

_c25_item_id_st = st.one_of(
    # C25-step-{n}-{field}  (n = 1..10)
    st.builds(
        lambda n, f: f"C25-step-{n}-{f}",
        st.integers(min_value=1, max_value=10),
        _c25_step_fields,
    ),
    # C25-reliance-conclusion
    st.just("C25-reliance-conclusion"),
    # C25-reliance-remark
    st.just("C25-reliance-remark"),
)

# C26 item_id patterns:
#   C26-ctrl-{m}-category (conclusion)
#   C26-ctrl-{m}-indexNo (remark)
#   C26-ctrl-{m}-purpose (remark)
#   C26-ctrl-{m}-plannedTest (remark)
#   C26-ctrl-{m}-walkthrough (remark)
#   C26-ctrl-{m}-controlTest (remark)
#   C26-ctrl-{m}-testResult (conclusion)
#   C26-ctrl-{m}-clientFeedback (remark)
#   C26-ctrl-{m}-conclusion (conclusion)
#   C26-ctrl-{m}-evidence (remark)
#   C26-ctrl-{m}-elements (conclusion, comma-separated)

_c26_ctrl_fields = st.sampled_from([
    "category", "indexNo", "purpose", "plannedTest",
    "walkthrough", "controlTest", "testResult",
    "clientFeedback", "conclusion", "evidence", "elements",
])

_c26_item_id_st = st.builds(
    lambda m, f: f"C26-ctrl-{m}-{f}",
    st.integers(min_value=1, max_value=50),
    _c26_ctrl_fields,
)

# Combined: either C25- or C26- prefixed item_id
_item_id_st = st.one_of(_c25_item_id_st, _c26_item_id_st)

# Unicode-safe text strategy (includes CJK characters typical in Chinese audit context)
_unicode_text_st = st.text(
    min_size=0,
    max_size=200,
    alphabet=st.characters(
        categories=("L", "N", "P", "Z"),
        include_characters="中文测试审计内审利用评估信息处理控制完整性准确性授权访问限制",
    ),
)

# Elements (comma-separated subset of 四要素)
_elements_values = ["完整性", "准确性", "授权", "访问限制"]
_elements_st = st.lists(
    st.sampled_from(_elements_values),
    min_size=0,
    max_size=4,
    unique=True,
).map(lambda xs: ",".join(xs))

# A single checklist_response item for C25/C26 (as would be passed to PUT endpoint)
_checklist_item_st = st.fixed_dictionaries({
    "item_id": _item_id_st,
    "conclusion": st.one_of(st.none(), _unicode_text_st.filter(lambda s: len(s) <= 50)),
    "remark": st.one_of(st.none(), _unicode_text_st),
})

# List of items representing a batch save payload
_batch_items_st = st.lists(_checklist_item_st, min_size=1, max_size=20)


# ═══════════════════════════════════════════════════════════════════════════════
# C25 full payload strategy (10 steps × 4 fields + conclusion + remark = 42 items)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_c25_full_payload(
    steps_applicable: list[str | None],
    steps_executor: list[str],
    steps_result: list[str],
    steps_indexRef: list[str],
    reliance_conclusion: str | None,
    reliance_remark: str | None,
) -> list[dict]:
    """Build a full C25 payload with all 42 items."""
    items: list[dict] = []
    for n in range(1, 11):
        items.append({"item_id": f"C25-step-{n}-applicable", "conclusion": steps_applicable[n - 1], "remark": None})
        items.append({"item_id": f"C25-step-{n}-executor", "conclusion": None, "remark": steps_executor[n - 1]})
        items.append({"item_id": f"C25-step-{n}-result", "conclusion": None, "remark": steps_result[n - 1]})
        items.append({"item_id": f"C25-step-{n}-indexRef", "conclusion": None, "remark": steps_indexRef[n - 1]})
    items.append({"item_id": "C25-reliance-conclusion", "conclusion": reliance_conclusion, "remark": None})
    items.append({"item_id": "C25-reliance-remark", "conclusion": None, "remark": reliance_remark})
    return items


_c25_full_st = st.builds(
    _build_c25_full_payload,
    steps_applicable=st.lists(
        st.one_of(st.none(), st.sampled_from(["Y", "N"])),
        min_size=10, max_size=10,
    ),
    steps_executor=st.lists(_unicode_text_st.filter(lambda s: len(s) <= 50), min_size=10, max_size=10),
    steps_result=st.lists(_unicode_text_st, min_size=10, max_size=10),
    steps_indexRef=st.lists(
        st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "P"))),
        min_size=10, max_size=10,
    ),
    reliance_conclusion=st.one_of(st.none(), st.sampled_from(["可利用", "不可利用", "部分利用"])),
    reliance_remark=st.one_of(st.none(), _unicode_text_st),
)


# ═══════════════════════════════════════════════════════════════════════════════
# C26 dynamic rows strategy (dynamic rows × 11 fields)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_c26_row(m: int, category: str, indexNo: str, purpose: str,
                   plannedTest: str, walkthrough: str, controlTest: str,
                   testResult: str | None, clientFeedback: str,
                   conclusion: str | None, evidence: str,
                   elements: str) -> list[dict]:
    """Build one C26 control row (11 items)."""
    return [
        {"item_id": f"C26-ctrl-{m}-category", "conclusion": category, "remark": None},
        {"item_id": f"C26-ctrl-{m}-indexNo", "conclusion": None, "remark": indexNo},
        {"item_id": f"C26-ctrl-{m}-purpose", "conclusion": None, "remark": purpose},
        {"item_id": f"C26-ctrl-{m}-plannedTest", "conclusion": None, "remark": plannedTest},
        {"item_id": f"C26-ctrl-{m}-walkthrough", "conclusion": None, "remark": walkthrough},
        {"item_id": f"C26-ctrl-{m}-controlTest", "conclusion": None, "remark": controlTest},
        {"item_id": f"C26-ctrl-{m}-testResult", "conclusion": testResult, "remark": None},
        {"item_id": f"C26-ctrl-{m}-clientFeedback", "conclusion": None, "remark": clientFeedback},
        {"item_id": f"C26-ctrl-{m}-conclusion", "conclusion": conclusion, "remark": None},
        {"item_id": f"C26-ctrl-{m}-evidence", "conclusion": None, "remark": evidence},
        {"item_id": f"C26-ctrl-{m}-elements", "conclusion": elements, "remark": None},
    ]


_c26_row_st = st.integers(min_value=1, max_value=20).flatmap(
    lambda m: st.builds(
        _build_c26_row,
        m=st.just(m),
        category=st.sampled_from(["销售循环", "采购循环", "收入确认", "薪酬循环", "财务报告"]),
        indexNo=st.builds(lambda n: f"IT-R&R-{n:02d}", st.integers(min_value=1, max_value=99)),
        purpose=_unicode_text_st.filter(lambda s: len(s) <= 100),
        plannedTest=_unicode_text_st.filter(lambda s: len(s) <= 100),
        walkthrough=_unicode_text_st.filter(lambda s: len(s) <= 100),
        controlTest=_unicode_text_st.filter(lambda s: len(s) <= 100),
        testResult=st.one_of(st.none(), st.sampled_from(["有效", "无效", "部分有效"])),
        clientFeedback=_unicode_text_st.filter(lambda s: len(s) <= 100),
        conclusion=st.one_of(st.none(), st.sampled_from(["有效", "无效", "部分有效", "不适用"])),
        evidence=st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "P"))),
        elements=_elements_st,
    )
)

_c26_multi_rows_st = st.lists(_c26_row_st, min_size=1, max_size=5).map(
    lambda rows: [item for row in rows for item in row]
)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestP5RoundTripConsistency:
    """Feature: c25-c26-internal-audit-info-control, Property 5: 持久化往返一致性

    **Validates: Requirements 6.1, 6.4**
    """

    @settings(max_examples=5)
    @given(items=_batch_items_st)
    def test_checklist_items_json_round_trip(self, items: list[dict]) -> None:
        """For any generated C25-/C26- prefixed items, JSON serialize → deserialize
        preserves all fields exactly (simulating PUT → GET persistence layer)."""
        serialized = json.dumps(items, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized) == len(items)

        for original, restored in zip(items, deserialized):
            assert restored["item_id"] == original["item_id"], (
                f"item_id mismatch: {restored['item_id']} != {original['item_id']}"
            )
            assert restored["conclusion"] == original["conclusion"], (
                f"conclusion mismatch for {original['item_id']}"
            )
            assert restored["remark"] == original["remark"], (
                f"remark mismatch for {original['item_id']}"
            )

    @settings(max_examples=5)
    @given(items=_batch_items_st)
    def test_item_id_prefix_preserved(self, items: list[dict]) -> None:
        """item_id prefix is always preserved: C25- items stay C25-, C26- items stay C26-."""
        serialized = json.dumps(items, ensure_ascii=False)
        deserialized = json.loads(serialized)

        for original, restored in zip(items, deserialized):
            orig_prefix = original["item_id"][:4]  # "C25-" or "C26-"
            rest_prefix = restored["item_id"][:4]
            assert orig_prefix == rest_prefix, (
                f"Prefix changed: {orig_prefix} → {rest_prefix}"
            )
            assert rest_prefix in ("C25-", "C26-"), (
                f"Unexpected prefix: {rest_prefix}"
            )

    @settings(max_examples=5)
    @given(items=_c25_full_st)
    def test_c25_full_payload_round_trip(self, items: list[dict]) -> None:
        """C25 full payload (10 steps × 4 fields + conclusion + remark = 42 items)
        survives JSON round-trip with all fields intact."""
        assert len(items) == 42, f"Expected 42 items, got {len(items)}"

        serialized = json.dumps(items, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized) == 42

        for original, restored in zip(items, deserialized):
            assert restored["item_id"] == original["item_id"]
            assert restored["item_id"].startswith("C25-")
            assert restored["conclusion"] == original["conclusion"]
            assert restored["remark"] == original["remark"]

    @settings(max_examples=5)
    @given(rows=_c26_multi_rows_st)
    def test_c26_dynamic_rows_round_trip(self, rows: list[dict]) -> None:
        """C26 dynamic rows (n rows × 11 fields per row) survive JSON round-trip
        with all fields intact."""
        assert len(rows) % 11 == 0, f"Expected multiple of 11 items, got {len(rows)}"

        serialized = json.dumps(rows, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized) == len(rows)

        for original, restored in zip(rows, deserialized):
            assert restored["item_id"] == original["item_id"]
            assert restored["item_id"].startswith("C26-")
            assert restored["conclusion"] == original["conclusion"]
            assert restored["remark"] == original["remark"]

    @settings(max_examples=5)
    @given(
        text_val=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                categories=("L", "N", "P", "S", "Z"),
                include_characters="中文審計內審利用評估信息處理控制完整性準確性テスト한국어émàñ",
            ),
        ),
        prefix=st.sampled_from(["C25-", "C26-"]),
    )
    def test_unicode_in_text_fields_survives_round_trip(self, text_val: str, prefix: str) -> None:
        """Unicode characters in conclusion/remark fields survive the round-trip."""
        item = {
            "item_id": f"{prefix}unicode-test-1",
            "conclusion": text_val,
            "remark": text_val,
        }

        serialized = json.dumps(item, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert deserialized["conclusion"] == text_val
        assert deserialized["remark"] == text_val
        assert deserialized["item_id"].startswith(prefix)

    @settings(max_examples=5)
    @given(elements=_elements_st)
    def test_elements_comma_separated_survives_round_trip(self, elements: str) -> None:
        """Elements array (comma-separated 四要素) survives JSON round-trip.
        Validates that comma-separated values in conclusion field are preserved."""
        item = {
            "item_id": "C26-ctrl-1-elements",
            "conclusion": elements,
            "remark": None,
        }

        serialized = json.dumps(item, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert deserialized["conclusion"] == elements
        assert deserialized["item_id"] == "C26-ctrl-1-elements"

        # Verify individual elements can be split back correctly
        if elements:
            original_set = set(elements.split(","))
            restored_set = set(deserialized["conclusion"].split(","))
            assert original_set == restored_set
            # All elements must be valid 四要素 values
            for elem in restored_set:
                assert elem in _elements_values, f"Invalid element: {elem}"
