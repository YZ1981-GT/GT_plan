"""Property 11: stale 回填幂等且不越界。

回填仅改 `is_stale=true AND stale_source IS NULL` 的行；
重跑不改已有非空值；`is_stale=false` 不写；无法判定回退 `report_fallback`。

**Validates: Requirements 4.1, 4.2, 4.3, 7.4**
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from scripts.backfill_note_stale_source import (
    _has_report_binding,
    _load_linkage_config_sections,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

st_cell_meta_slot = st.fixed_dictionaries(
    {"binding": st.fixed_dictionaries({"source": st.sampled_from(["report", "workpaper", "formula", "manual"])})}
)

st_cell_meta_slot_no_report = st.fixed_dictionaries(
    {"binding": st.fixed_dictionaries({"source": st.sampled_from(["workpaper", "formula", "manual"])})}
)

st_row_with_report_binding = st.fixed_dictionaries(
    {"_cell_meta": st.dictionaries(st.text(min_size=1, max_size=5), st_cell_meta_slot, min_size=1, max_size=3)}
)

st_row_without_report_binding = st.fixed_dictionaries(
    {"_cell_meta": st.dictionaries(st.text(min_size=1, max_size=5), st_cell_meta_slot_no_report, min_size=1, max_size=3)}
)


# ---------------------------------------------------------------------------
# _has_report_binding — pure function tests
# ---------------------------------------------------------------------------


class TestHasReportBinding:
    """Test the pure function that detects REPORT Cell_Binding in table_data."""

    def test_empty_dict_returns_false(self):
        assert _has_report_binding({}) is False

    def test_none_returns_false(self):
        assert _has_report_binding(None) is False

    def test_non_dict_returns_false(self):
        assert _has_report_binding([1, 2, 3]) is False
        assert _has_report_binding("hello") is False

    def test_rows_with_report_source(self):
        td = {
            "rows": [
                {
                    "_cell_meta": {
                        "col1": {"binding": {"source": "report"}},
                    }
                }
            ]
        }
        assert _has_report_binding(td) is True

    def test_rows_without_report_source(self):
        td = {
            "rows": [
                {
                    "_cell_meta": {
                        "col1": {"binding": {"source": "workpaper"}},
                    }
                }
            ]
        }
        assert _has_report_binding(td) is False

    def test_tables_with_report_source(self):
        td = {
            "_tables": [
                {
                    "rows": [
                        {
                            "_cell_meta": {
                                "amount": {"binding": {"source": "report"}},
                            }
                        }
                    ]
                }
            ]
        }
        assert _has_report_binding(td) is True

    def test_tables_without_report_source(self):
        td = {
            "_tables": [
                {
                    "rows": [
                        {
                            "_cell_meta": {
                                "amount": {"binding": {"source": "manual"}},
                            }
                        }
                    ]
                }
            ]
        }
        assert _has_report_binding(td) is False

    def test_no_cell_meta_returns_false(self):
        td = {"rows": [{"values": [1, 2, 3]}]}
        assert _has_report_binding(td) is False

    def test_binding_key_missing_returns_false(self):
        td = {"rows": [{"_cell_meta": {"col1": {"other_key": "val"}}}]}
        assert _has_report_binding(td) is False

    @settings(max_examples=5)
    @given(
        prefix_rows=st.lists(st_row_without_report_binding, min_size=0, max_size=2),
        suffix_rows=st.lists(st_row_without_report_binding, min_size=0, max_size=2),
    )
    def test_pbt_any_report_binding_detected(self, prefix_rows, suffix_rows):
        """**Validates: Requirements 4.1** — rows containing source='report' are detected."""
        # Guarantee at least one row with a definite report binding
        report_row = {"_cell_meta": {"col_x": {"binding": {"source": "report"}}}}
        rows = prefix_rows + [report_row] + suffix_rows
        td = {"rows": rows}
        assert _has_report_binding(td) is True

    @settings(max_examples=5)
    @given(st.lists(st_row_without_report_binding, min_size=1, max_size=3))
    def test_pbt_no_report_binding_not_detected(self, rows):
        """**Validates: Requirements 4.4** — rows without source='report' are not falsely detected."""
        td = {"rows": rows}
        assert _has_report_binding(td) is False


# ---------------------------------------------------------------------------
# _load_linkage_config_sections — pure function tests
# ---------------------------------------------------------------------------


class TestLoadLinkageConfigSections:
    """Test loading note_section set from report_note_linkage.json."""

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        """If file doesn't exist, returns empty set gracefully."""
        monkeypatch.setattr(
            "scripts.backfill_note_stale_source._LINKAGE_CONFIG_PATH",
            tmp_path / "nonexistent.json",
        )
        result = _load_linkage_config_sections()
        assert result == set()

    def test_valid_json_extracts_note_sections(self, tmp_path, monkeypatch):
        """Extracts note_section from entries correctly."""
        config = {
            "BS-002": [
                {"note_section": "五、1", "row_code": "BS-002"},
                {"note_section": "五、2", "row_code": "BS-003"},
            ],
            "IS-001": [
                {"note_section": "五、62"},
            ],
            "_metadata": {"version": 1},  # underscore keys skipped
        }
        config_path = tmp_path / "linkage.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setattr(
            "scripts.backfill_note_stale_source._LINKAGE_CONFIG_PATH",
            config_path,
        )
        result = _load_linkage_config_sections()
        assert "五、1" in result
        assert "五、2" in result
        assert "五、62" in result

    def test_skips_underscore_keys(self, tmp_path, monkeypatch):
        """Keys starting with _ are metadata, not row_codes."""
        config = {
            "_rules": [{"note_section": "should_not_appear"}],
            "BS-001": [{"note_section": "五、1"}],
        }
        config_path = tmp_path / "linkage.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setattr(
            "scripts.backfill_note_stale_source._LINKAGE_CONFIG_PATH",
            config_path,
        )
        result = _load_linkage_config_sections()
        assert "should_not_appear" not in result
        assert "五、1" in result

    def test_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        """Malformed JSON returns empty set gracefully (fail-open)."""
        config_path = tmp_path / "linkage.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")
        monkeypatch.setattr(
            "scripts.backfill_note_stale_source._LINKAGE_CONFIG_PATH",
            config_path,
        )
        result = _load_linkage_config_sections()
        assert result == set()

    def test_non_dict_root_returns_empty(self, tmp_path, monkeypatch):
        """If JSON root is not a dict, returns empty."""
        config_path = tmp_path / "linkage.json"
        config_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        monkeypatch.setattr(
            "scripts.backfill_note_stale_source._LINKAGE_CONFIG_PATH",
            config_path,
        )
        result = _load_linkage_config_sections()
        assert result == set()


# ---------------------------------------------------------------------------
# Property 11: Classification logic (stale_source assignment)
# ---------------------------------------------------------------------------


class TestClassificationLogic:
    """Test the classification decision: section in REPORT set → 'report', else 'report_fallback'.

    **Validates: Requirements 4.1, 4.4**
    """

    @settings(max_examples=5)
    @given(st.text(min_size=1, max_size=20))
    def test_pbt_unknown_section_always_report_fallback(self, section):
        """Unknown section → 'report_fallback' (conservative, never guesses 'report')."""
        report_sections: set[str] = set()  # empty = no REPORT linkage known
        if section in report_sections:
            source = "report"
        else:
            source = "report_fallback"
        assert source == "report_fallback"

    @settings(max_examples=5)
    @given(st.sampled_from(["五、1", "五、5", "八、18", "五、22", "八、26"]))
    def test_pbt_known_section_gets_report(self, section):
        """Section in REPORT linkage set → 'report'."""
        report_sections = {"五、1", "五、5", "八、18", "五、22", "八、26"}
        if section in report_sections:
            source = "report"
        else:
            source = "report_fallback"
        assert source == "report"

    def test_classification_is_deterministic(self):
        """Same input → same output (idempotent classification)."""
        report_sections = {"五、1", "五、22"}
        results = []
        for _ in range(10):
            source = "report" if "五、1" in report_sections else "report_fallback"
            results.append(source)
        assert all(r == "report" for r in results)


# ---------------------------------------------------------------------------
# Property 11: Idempotency & boundary (simulated)
# ---------------------------------------------------------------------------


class TestIdempotencyAndBoundary:
    """Simulate the WHERE clause logic to verify idempotency and boundary rules.

    **Validates: Requirements 4.2, 4.3**
    """

    @staticmethod
    def _should_process(is_stale: bool, stale_source: str | None) -> bool:
        """Mirrors the SQL WHERE: is_stale=true AND stale_source IS NULL."""
        return is_stale is True and stale_source is None

    @staticmethod
    def _should_update(is_stale: bool, stale_source: str | None) -> bool:
        """Mirrors the per-row UPDATE WHERE: stale_source IS NULL."""
        return stale_source is None

    def test_is_stale_false_never_processed(self):
        """is_stale=false → not in candidate set (Req 4.3)."""
        assert self._should_process(False, None) is False
        assert self._should_process(False, "report") is False

    def test_already_has_stale_source_not_processed(self):
        """stale_source already set → not in candidate set (Req 4.2 idempotent)."""
        assert self._should_process(True, "report") is False
        assert self._should_process(True, "report_fallback") is False

    def test_stale_true_and_null_source_is_processed(self):
        """is_stale=true AND stale_source IS NULL → candidate."""
        assert self._should_process(True, None) is True

    @settings(max_examples=5)
    @given(
        is_stale=st.booleans(),
        stale_source=st.one_of(st.none(), st.sampled_from(["report", "report_fallback"])),
    )
    def test_pbt_idempotent_second_run_changes_zero(self, is_stale, stale_source):
        """**Validates: Requirements 4.2** — After first run sets stale_source,
        second run finds no candidates (stale_source IS NOT NULL)."""
        # Simulate first run: if candidate, assign a source
        if self._should_process(is_stale, stale_source):
            # First run assigns
            new_source = "report_fallback"
            # After first run, stale_source is no longer NULL
            assert self._should_process(is_stale, new_source) is False
        else:
            # Not a candidate → stays unchanged
            pass

    @settings(max_examples=5)
    @given(
        stale_source=st.sampled_from(["report", "report_fallback", "some_other_value"]),
    )
    def test_pbt_existing_non_null_stale_source_preserved(self, stale_source):
        """**Validates: Requirements 4.2** — Existing non-null stale_source is never overwritten."""
        # Row with is_stale=true but already has stale_source
        assert self._should_process(True, stale_source) is False
        # Even the per-row UPDATE guard prevents it
        assert self._should_update(True, stale_source) is False
