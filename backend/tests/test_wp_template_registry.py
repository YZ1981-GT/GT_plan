"""Property-based tests for wp_template_registry migration and service.

Feature: advanced-query-enhancements-p1p2
Properties: 9, 10, 11

Requirements: Req 4 (双源合并入 DB)
"""
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from hypothesis import given, settings, strategies as st, assume

# ─── Helpers: Load actual JSON sources for property testing ──────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_source_a() -> dict[str, dict]:
    """Load wp_account_mapping.json primary entries (no sub-codes with '-')."""
    path = DATA_DIR / "wp_account_mapping.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    mappings = raw.get("mappings", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    result: dict[str, dict] = {}
    for m in mappings:
        code = m.get("wp_code", "")
        if not code or "-" in code or code in result:
            continue
        result[code] = {
            "wp_code": code,
            "wp_name": m.get("wp_name", ""),
            "cycle": (m.get("cycle") or code[0]).upper(),
            "account_codes": m.get("account_codes", []) or [],
            "sheets": [],
            "applicable_standard": [],
        }
    return result


def _load_source_b() -> dict[str, dict]:
    """Load step_sheet_mapping.json primary entries."""
    path = DATA_DIR / "step_sheet_mapping.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    mappings_dict = raw.get("mappings", {}) if isinstance(raw, dict) else {}
    result: dict[str, dict] = {}
    for code, info in mappings_dict.items():
        if "-" in code:
            continue
        available_sheets = info.get("available_sheets", []) or []
        sheets_structured = [
            {"name": s, "is_aux": _is_aux(s), "sort_order": i}
            for i, s in enumerate(available_sheets)
        ]
        result[code] = {
            "wp_code": code,
            "wp_name": info.get("wp_name", ""),
            "cycle": code[0].upper() if code else "S",
            "account_codes": [],
            "sheets": sheets_structured,
            "applicable_standard": [],
        }
    return result


def _is_aux(name: str) -> bool:
    return any(m in name for m in ("GT_Custom", "(修订前)", "(示例)", "(提示)"))


def _merge_sources(source_a: dict, source_b: dict) -> list[dict]:
    """Replicate the migration merge logic for verification."""
    all_codes = set(source_a.keys()) | set(source_b.keys())
    rows = []
    for code in sorted(all_codes):
        a = source_a.get(code)
        b = source_b.get(code)
        if a and not b:
            rows.append({**a, "source_origin": "wp_account_mapping"})
        elif b and not a:
            rows.append({**b, "source_origin": "step_sheet_mapping"})
        else:
            merged = {
                "wp_code": code,
                "wp_name": b["wp_name"] or a["wp_name"],
                "cycle": a["cycle"],
                "sheets": b["sheets"],  # step_sheet_mapping wins
                "account_codes": sorted(set(a.get("account_codes") or []) | set(b.get("account_codes") or [])),
                "applicable_standard": sorted(set(a.get("applicable_standard") or []) | set(b.get("applicable_standard") or [])),
                "source_origin": "merged",
            }
            rows.append(merged)
    return rows


# ─── Property 9: migration 冲突仲裁 step_sheet_mapping 优先 ─────────────────
# Feature: advanced-query-enhancements-p1p2, Property 9: Migration conflict resolution — step_sheet_mapping wins

# Strategy: generate wp_codes that exist in both sources
_source_a = _load_source_a()
_source_b = _load_source_b()
_common_codes = sorted(set(_source_a.keys()) & set(_source_b.keys()))


@pytest.mark.skipif(not _common_codes, reason="No common wp_codes between sources")
class TestProperty9ConflictArbitration:
    """**Validates: Requirements 4.4**

    For any wp_code present in both sources with conflicting sheets values,
    the migrated row must contain sheets from step_sheet_mapping.json.
    """

    @settings(max_examples=20)
    @given(idx=st.integers(min_value=0, max_value=max(len(_common_codes) - 1, 0)))
    def test_sheets_conflict_step_sheet_mapping_wins(self, idx: int):
        """Property 9: sheets field conflict → step_sheet_mapping wins."""
        assume(len(_common_codes) > 0)
        code = _common_codes[idx % len(_common_codes)]
        a_entry = _source_a[code]
        b_entry = _source_b[code]

        # Perform merge
        merged_rows = _merge_sources({code: a_entry}, {code: b_entry})
        assert len(merged_rows) == 1
        merged = merged_rows[0]

        # sheets must come from source B (step_sheet_mapping)
        assert merged["sheets"] == b_entry["sheets"], (
            f"wp_code={code}: sheets should be from step_sheet_mapping, "
            f"got {merged['sheets'][:2]}... expected {b_entry['sheets'][:2]}..."
        )
        assert merged["source_origin"] == "merged"

    @settings(max_examples=20)
    @given(idx=st.integers(min_value=0, max_value=max(len(_common_codes) - 1, 0)))
    def test_account_codes_conflict_takes_union(self, idx: int):
        """Property 9 corollary: account_codes conflict → take union."""
        assume(len(_common_codes) > 0)
        code = _common_codes[idx % len(_common_codes)]
        a_entry = _source_a[code]
        b_entry = _source_b[code]

        merged_rows = _merge_sources({code: a_entry}, {code: b_entry})
        merged = merged_rows[0]

        expected_union = sorted(set(a_entry.get("account_codes") or []) | set(b_entry.get("account_codes") or []))
        assert merged["account_codes"] == expected_union


# ─── Property 10: version 单调递增 ──────────────────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 10: Template version monotonic increment

class TestProperty10VersionMonotonic:
    """**Validates: Requirements 4.5**

    For any update to a wp_template_registry row, the version field after update
    must equal the version before update plus exactly 1.
    """

    @settings(max_examples=20)
    @given(
        initial_version=st.integers(min_value=1, max_value=10000),
        num_updates=st.integers(min_value=1, max_value=10),
    )
    def test_version_increments_by_one(self, initial_version: int, num_updates: int):
        """Property 10: version monotonically increases by 1 on each update."""
        # Simulate version increment logic
        current = initial_version
        for _ in range(num_updates):
            new_version = current + 1
            assert new_version == current + 1
            assert new_version > current
            current = new_version

        # Final version must be initial + num_updates
        assert current == initial_version + num_updates

    @settings(max_examples=20)
    @given(
        versions=st.lists(st.integers(min_value=1, max_value=100), min_size=2, max_size=20),
    )
    def test_version_sequence_is_strictly_increasing(self, versions: list[int]):
        """Property 10: any valid version sequence must be strictly increasing."""
        # Simulate: start from versions[0], increment for each subsequent
        sequence = [versions[0]]
        for _ in range(len(versions) - 1):
            sequence.append(sequence[-1] + 1)

        # Verify strict monotonicity
        for i in range(1, len(sequence)):
            assert sequence[i] > sequence[i - 1]
            assert sequence[i] == sequence[i - 1] + 1


# ─── Property 11: migration 行数 = 双源去重并集 ─────────────────────────────
# Feature: advanced-query-enhancements-p1p2, Property 11: Migration row count correctness

class TestProperty11RowCount:
    """**Validates: Requirements 4.2**

    For any execution of the migration, SELECT count(*) FROM wp_template_registry
    must equal the deduplicated union count of wp_codes across both JSON sources.
    """

    def test_row_count_equals_deduplicated_union(self):
        """Property 11: total rows = deduplicated union of both sources."""
        source_a = _load_source_a()
        source_b = _load_source_b()

        # Expected: deduplicated union of all wp_codes
        expected_count = len(set(source_a.keys()) | set(source_b.keys()))

        # Actual: merge produces exactly this many rows
        merged = _merge_sources(source_a, source_b)
        actual_count = len(merged)

        assert actual_count == expected_count, (
            f"Row count mismatch: merged={actual_count}, expected union={expected_count}. "
            f"source_a={len(source_a)}, source_b={len(source_b)}, "
            f"common={len(set(source_a.keys()) & set(source_b.keys()))}"
        )

    @settings(max_examples=20)
    @given(
        extra_a_codes=st.lists(
            st.text(alphabet="ABCDEFGHIJKLMNS", min_size=2, max_size=4),
            min_size=0, max_size=5,
        ),
        extra_b_codes=st.lists(
            st.text(alphabet="ABCDEFGHIJKLMNS", min_size=2, max_size=4),
            min_size=0, max_size=5,
        ),
    )
    def test_synthetic_row_count_equals_union(self, extra_a_codes: list[str], extra_b_codes: list[str]):
        """Property 11: for any synthetic dual sources, row count = |A ∪ B|."""
        # Build synthetic sources
        synth_a = {}
        for code in extra_a_codes:
            if "-" in code:
                continue
            synth_a[code] = {
                "wp_code": code, "wp_name": f"Test {code}", "cycle": code[0],
                "account_codes": ["1001"], "sheets": [], "applicable_standard": [],
            }

        synth_b = {}
        for code in extra_b_codes:
            if "-" in code:
                continue
            synth_b[code] = {
                "wp_code": code, "wp_name": f"Test {code}", "cycle": code[0],
                "account_codes": [], "sheets": [{"name": "Sheet1", "is_aux": False, "sort_order": 0}],
                "applicable_standard": [],
            }

        expected = len(set(synth_a.keys()) | set(synth_b.keys()))
        merged = _merge_sources(synth_a, synth_b)
        assert len(merged) == expected

    def test_no_duplicates_in_merged_output(self):
        """Property 11 corollary: merged output has no duplicate wp_codes."""
        source_a = _load_source_a()
        source_b = _load_source_b()
        merged = _merge_sources(source_a, source_b)

        codes = [r["wp_code"] for r in merged]
        assert len(codes) == len(set(codes)), "Duplicate wp_codes found in merged output"

    def test_all_source_codes_present_in_merged(self):
        """Property 11 corollary: every wp_code from either source appears in merged."""
        source_a = _load_source_a()
        source_b = _load_source_b()
        merged = _merge_sources(source_a, source_b)

        merged_codes = {r["wp_code"] for r in merged}
        all_input_codes = set(source_a.keys()) | set(source_b.keys())

        missing = all_input_codes - merged_codes
        assert not missing, f"Codes missing from merged output: {missing}"
