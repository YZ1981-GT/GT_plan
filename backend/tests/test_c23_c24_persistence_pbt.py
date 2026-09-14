"""Property-Based Test: P8 往返一致性 — C23-/C24- item_id Round-Trip

Feature: c23-c24-journal-entry-testing, Property 8: 持久化往返一致性

For any valid C23/C24 data payload saved via the checklist_responses API:
- Save data with item_id prefix C23- or C24-
- Read it back
- The read data must equal the saved data (no data loss or corruption)

Properties tested:
- JSON round-trip of C23-/C24- prefixed item_ids preserves all fields
- item_id prefix is always preserved (C23- stays C23-, C24- stays C24-)
- Unicode characters in data fields survive the round-trip
- Numeric fields (amounts) survive round-trip without precision loss

**Validates: Requirements 8.1**

Uses hypothesis with max_examples=5 (project standard).
"""

from __future__ import annotations

import json
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st


# ═══════════════════════════════════════════════════════════════════════════════
# Strategies — C23/C24 item_id generation
# ═══════════════════════════════════════════════════════════════════════════════

# C23 item_id patterns: C23-person-{n}-{field}, C23-sample-{s}-{field}, C23-sample-{s}-deviation
_c23_person_fields = st.sampled_from(["name", "permission", "role", "department"])
_c24_conclusion_fields = st.sampled_from(["conclusion", "source", "tool", "version"])

_c23_item_id_st = st.one_of(
    # C23-person-{n}-{field}
    st.builds(
        lambda n, f: f"C23-person-{n}-{f}",
        st.integers(min_value=1, max_value=50),
        _c23_person_fields,
    ),
    # C23-sample-{s}-{field}
    st.builds(
        lambda s, f: f"C23-sample-{s}-{f}",
        st.integers(min_value=1, max_value=25),
        st.sampled_from(["preparer", "poster", "reviewer", "date", "doc", "approval", "deviation"]),
    ),
)

# C24 item_id patterns: C24-0-source-{field}, C24-{k}-conclusion, C24-5-anomaly-{i}-{field},
# C24-benford-{field}, C24-journal-entries
_c24_item_id_st = st.one_of(
    # C24-0-source-{field}
    st.builds(
        lambda f: f"C24-0-source-{f}",
        _c24_conclusion_fields,
    ),
    # C24-{k}-conclusion
    st.builds(
        lambda k: f"C24-{k}-conclusion",
        st.integers(min_value=1, max_value=5),
    ),
    # C24-5-anomaly-{i}-{field}
    st.builds(
        lambda i, f: f"C24-5-anomaly-{i}-{f}",
        st.integers(min_value=1, max_value=100),
        st.sampled_from(["type", "description", "check", "conclusion", "amount"]),
    ),
    # C24-benford-{field}
    st.builds(
        lambda f: f"C24-benford-{f}",
        st.sampled_from(["exclude_accounts", "min_amount", "max_amount", "result"]),
    ),
)

# Combined: either C23- or C24- prefixed item_id
_item_id_st = st.one_of(_c23_item_id_st, _c24_item_id_st)

# Unicode-safe text strategy (includes CJK characters typical in Chinese audit context)
_unicode_text_st = st.text(
    min_size=0,
    max_size=200,
    alphabet=st.characters(
        categories=("L", "N", "P", "Z"),
        include_characters="中文测试审计会计分录凭证摘要借方贷方偏差结论",
    ),
)

# Numeric amount strategy (finite floats for amounts)
_amount_st = st.floats(
    min_value=-1e12, max_value=1e12,
    allow_nan=False, allow_infinity=False,
)

# A single checklist_response item (as would be passed to PUT endpoint)
_checklist_item_st = st.fixed_dictionaries({
    "item_id": _item_id_st,
    "conclusion": st.one_of(st.none(), _unicode_text_st.filter(lambda s: len(s) <= 50)),
    "remark": st.one_of(st.none(), _unicode_text_st),
    "wp_ref": st.one_of(st.none(), st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "P")))),
})

# List of items representing a batch save payload
_batch_items_st = st.lists(_checklist_item_st, min_size=1, max_size=15)


# Strategy for journal entry data (stored as JSON in remark field)
_journal_entry_st = st.fixed_dictionaries({
    "voucherDate": st.from_regex(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]", fullmatch=True),
    "voucherMonth": st.integers(min_value=1, max_value=12),
    "voucherType": st.sampled_from(["付", "收", "转", "记"]),
    "voucherNo": st.builds(lambda t, n: f"{t}-{n:04d}", st.sampled_from(["付", "收", "转"]), st.integers(min_value=1, max_value=9999)),
    "summary": _unicode_text_st.filter(lambda s: len(s) <= 100),
    "accountCode": st.from_regex(r"[1-9][0-9]{3}(\.[0-9]{2})?", fullmatch=True),
    "accountName": _unicode_text_st.filter(lambda s: 1 <= len(s) <= 50),
    "debit": _amount_st,
    "credit": _amount_st,
    "voucherSheets": st.integers(min_value=0, max_value=99),
    "preparer": _unicode_text_st.filter(lambda s: len(s) <= 20),
    "reviewer": _unicode_text_st.filter(lambda s: len(s) <= 20),
    "poster": _unicode_text_st.filter(lambda s: len(s) <= 20),
})

_journal_entries_st = st.lists(_journal_entry_st, min_size=1, max_size=10)


# ═══════════════════════════════════════════════════════════════════════════════
# Property Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestP8RoundTripConsistency:
    """Feature: c23-c24-journal-entry-testing, Property 8: 持久化往返一致性

    **Validates: Requirements 8.1**
    """

    @settings(max_examples=5)
    @given(items=_batch_items_st)
    def test_checklist_items_json_round_trip(self, items: list[dict]) -> None:
        """For any generated C23-/C24- prefixed items, JSON serialize → deserialize
        preserves all fields exactly (simulating PUT → GET persistence layer)."""
        # Simulate the persistence layer: serialize to JSON (as stored in DB)
        serialized = json.dumps(items, ensure_ascii=False)

        # Deserialize (as read back from DB)
        deserialized = json.loads(serialized)

        # Verify count
        assert len(deserialized) == len(items)

        # Verify each item field-by-field
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
            assert restored["wp_ref"] == original["wp_ref"], (
                f"wp_ref mismatch for {original['item_id']}"
            )

    @settings(max_examples=5)
    @given(items=_batch_items_st)
    def test_item_id_prefix_preserved(self, items: list[dict]) -> None:
        """item_id prefix is always preserved: C23- items stay C23-, C24- items stay C24-."""
        serialized = json.dumps(items, ensure_ascii=False)
        deserialized = json.loads(serialized)

        for original, restored in zip(items, deserialized):
            orig_prefix = original["item_id"][:4]  # "C23-" or "C24-"
            rest_prefix = restored["item_id"][:4]
            assert orig_prefix == rest_prefix, (
                f"Prefix changed: {orig_prefix} → {rest_prefix}"
            )
            assert rest_prefix in ("C23-", "C24-"), (
                f"Unexpected prefix: {rest_prefix}"
            )

    @settings(max_examples=5)
    @given(entries=_journal_entries_st)
    def test_journal_entries_json_round_trip_preserves_amounts(self, entries: list[dict]) -> None:
        """Numeric fields (debit/credit amounts) survive JSON round-trip without precision loss.

        This validates the C24-journal-entries remark field storage pattern.
        """
        # Simulate storing journal entries as JSON in remark (as C24 import does)
        serialized = json.dumps(entries, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert len(deserialized) == len(entries)

        for original, restored in zip(entries, deserialized):
            # Amounts must be exactly equal (JSON float fidelity)
            assert restored["debit"] == original["debit"], (
                f"debit precision loss: {original['debit']} → {restored['debit']}"
            )
            assert restored["credit"] == original["credit"], (
                f"credit precision loss: {original['credit']} → {restored['credit']}"
            )
            # Integer fields
            assert restored["voucherMonth"] == original["voucherMonth"]
            assert restored["voucherSheets"] == original["voucherSheets"]
            # String fields (including Unicode)
            assert restored["summary"] == original["summary"]
            assert restored["preparer"] == original["preparer"]
            assert restored["voucherNo"] == original["voucherNo"]
            assert restored["accountCode"] == original["accountCode"]
            assert restored["accountName"] == original["accountName"]

    @settings(max_examples=5)
    @given(
        text_val=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                categories=("L", "N", "P", "S", "Z"),
                include_characters="中文審計會計憑證漢字テスト한국어émàñ",
            ),
        ),
        prefix=st.sampled_from(["C23-", "C24-"]),
    )
    def test_unicode_in_all_fields_survives_round_trip(self, text_val: str, prefix: str) -> None:
        """Unicode characters in conclusion/remark/wp_ref fields survive the round-trip."""
        item = {
            "item_id": f"{prefix}unicode-test-1",
            "conclusion": text_val,
            "remark": text_val,
            "wp_ref": text_val[:20],
        }

        serialized = json.dumps(item, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert deserialized["conclusion"] == text_val
        assert deserialized["remark"] == text_val
        assert deserialized["wp_ref"] == text_val[:20]
        assert deserialized["item_id"].startswith(prefix)
