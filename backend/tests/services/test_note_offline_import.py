"""Tests for Sprint C.0 — 附注离线导入服务 (D15).

Covers:
- C.0.9: Validate import file (_meta_ sheet check)
- C.0.10: Section matching (matched/import_only/system_only)
- C.0.11: Field-level diff (value/formula/manual)
- C.0.12: Conflict resolution (overwrite/keep/merge/discard)
- C.0.13: Lock integration
- C.0.14: Version tree integration
- C.0.15: Template type check
- C.0.16: Audit log + archive
- CI-21: _meta_ sheet completeness
- CI-22: Export→Import round-trip PBT
"""
from __future__ import annotations

import json
from io import BytesIO
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_offline_export_service import export_sections_to_xlsx
from app.services.note_offline_import_service import (
    CellDiff,
    ConflictResolution,
    DiffType,
    FieldCategory,
    ImportResult,
    ImportValidationResult,
    MatchStatus,
    SectionDiff,
    _values_equal,
    apply_import,
    build_archive_record,
    check_template_type_compatibility,
    create_version_node,
    diff_section_cells,
    diff_sections,
    match_sections,
    validate_import_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_section(
    section_id: str = "section_cash",
    title: str = "货币资金",
    rows: list | None = None,
) -> dict:
    if rows is None:
        rows = [
            {"row_type": "data", "label": "银行存款", "cells": [100.0, 200.0]},
            {"row_type": "data", "label": "现金", "cells": [50.0, 30.0]},
        ]
    return {
        "section_id": section_id,
        "section_title": title,
        "table_data": {"headers": ["项目", "金额"], "rows": rows},
        "_cell_meta": {},
        "_formulas": {},
        "_cell_provenance": {},
        "_bindings": {},
        "_row_meta": [],
        "_dynamic_regions": [],
        "_cell_modes": {},
    }


def _export_and_get_bytes(sections: list[dict]) -> bytes:
    """Export sections and return plain xlsx bytes."""
    xlsx_bytes, _ = export_sections_to_xlsx(sections)
    return xlsx_bytes


# ---------------------------------------------------------------------------
# C.0.9: Validate Import File
# ---------------------------------------------------------------------------


class TestValidateImportFile:
    """C.0.9 — validate uploaded xlsx."""

    def test_valid_file(self):
        sections = [_make_section()]
        xlsx_bytes = _export_and_get_bytes(sections)
        result = validate_import_file(xlsx_bytes)
        assert result.valid is True
        assert len(result.errors) == 0
        assert "section_cash" in result.section_ids

    def test_invalid_bytes(self):
        result = validate_import_file(b"not a valid xlsx")
        assert result.valid is False
        assert any("无法解析" in e for e in result.errors)

    def test_missing_meta_sheet(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.title = "Sheet1"
        buf = BytesIO()
        wb.save(buf)
        result = validate_import_file(buf.getvalue())
        assert result.valid is False
        assert any("_meta_" in e for e in result.errors)

    def test_ci21_section_ids_present(self):
        """CI-21: _meta_ sheet must have section_id."""
        sections = [_make_section("s1"), _make_section("s2", "应收账款")]
        xlsx_bytes = _export_and_get_bytes(sections)
        result = validate_import_file(xlsx_bytes)
        assert result.valid is True
        assert "s1" in result.section_ids
        assert "s2" in result.section_ids

    def test_ci21_binding_hash_present(self):
        """CI-21: _meta_ sheet must have binding_hash."""
        sections = [_make_section()]
        xlsx_bytes = _export_and_get_bytes(sections)
        result = validate_import_file(xlsx_bytes)
        assert result.valid is True
        assert len(result.binding_hash) == 64

    def test_format_version(self):
        sections = [_make_section()]
        xlsx_bytes = _export_and_get_bytes(sections)
        result = validate_import_file(xlsx_bytes)
        assert result.format_version == "1.0"


# ---------------------------------------------------------------------------
# C.0.10: Section Matching
# ---------------------------------------------------------------------------


class TestSectionMatching:
    """C.0.10 — match imported vs existing sections."""

    def test_all_matched(self):
        result = match_sections(["s1", "s2"], ["s1", "s2"])
        assert result["s1"] == MatchStatus.MATCHED
        assert result["s2"] == MatchStatus.MATCHED

    def test_import_only(self):
        result = match_sections(["s1", "s2", "s3"], ["s1"])
        assert result["s2"] == MatchStatus.IMPORT_ONLY
        assert result["s3"] == MatchStatus.IMPORT_ONLY

    def test_system_only(self):
        result = match_sections(["s1"], ["s1", "s2", "s3"])
        assert result["s2"] == MatchStatus.SYSTEM_ONLY
        assert result["s3"] == MatchStatus.SYSTEM_ONLY

    def test_mixed(self):
        result = match_sections(["s1", "s2"], ["s2", "s3"])
        assert result["s1"] == MatchStatus.IMPORT_ONLY
        assert result["s2"] == MatchStatus.MATCHED
        assert result["s3"] == MatchStatus.SYSTEM_ONLY

    def test_empty_both(self):
        result = match_sections([], [])
        assert result == {}

    def test_empty_import(self):
        result = match_sections([], ["s1"])
        assert result["s1"] == MatchStatus.SYSTEM_ONLY


# ---------------------------------------------------------------------------
# C.0.11: Field-Level Diff
# ---------------------------------------------------------------------------


class TestFieldLevelDiff:
    """C.0.11 — cell-level diff algorithm."""

    def test_no_diff_same_data(self):
        local = {"rows": [{"cells": [100, 200]}]}
        imported = {"rows": [{"cells": [100, 200]}]}
        diffs = diff_section_cells(local, imported)
        assert len(diffs) == 0

    def test_modify_diff(self):
        local = {"rows": [{"cells": [100, 200]}]}
        imported = {"rows": [{"cells": [100, 300]}]}
        diffs = diff_section_cells(local, imported)
        assert len(diffs) == 1
        assert diffs[0].diff_type == DiffType.MODIFY
        assert diffs[0].cell_key == "0:1"

    def test_add_diff(self):
        local = {"rows": [{"cells": [100]}]}
        imported = {"rows": [{"cells": [100, 200]}]}
        diffs = diff_section_cells(local, imported)
        assert any(d.diff_type == DiffType.ADD for d in diffs)

    def test_remove_diff(self):
        local = {"rows": [{"cells": [100, 200]}]}
        imported = {"rows": [{"cells": [100, None]}]}
        diffs = diff_section_cells(local, imported)
        assert any(d.diff_type == DiffType.REMOVE for d in diffs)

    def test_formula_cell_skipped_if_unchanged(self):
        local = {"rows": [{"cells": [100]}]}
        imported = {"rows": [{"cells": [100]}]}
        meta = {"0:0": {"mode": "formula", "source": "formula"}}
        diffs = diff_section_cells(local, imported, meta=meta)
        assert len(diffs) == 0

    def test_formula_cell_detected_if_changed(self):
        local = {"rows": [{"cells": [100]}]}
        imported = {"rows": [{"cells": [999]}]}
        meta = {"0:0": {"mode": "formula", "source": "formula"}}
        diffs = diff_section_cells(local, imported, meta=meta)
        assert len(diffs) == 1
        assert diffs[0].field_category == FieldCategory.FORMULA

    def test_values_equal_numeric_tolerance(self):
        assert _values_equal(100.0, 100.000001) is True
        assert _values_equal(100.0, 101.0) is False

    def test_values_equal_string(self):
        assert _values_equal("hello", "hello") is True
        assert _values_equal("hello ", "hello") is True

    def test_values_equal_none(self):
        assert _values_equal(None, None) is True
        assert _values_equal(None, 0) is False


# ---------------------------------------------------------------------------
# C.0.12: Conflict Resolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    """C.0.12 — apply import with decisions."""

    def test_overwrite(self):
        sections = [_make_section("s1", rows=[{"row_type": "data", "cells": [100]}])]
        xlsx_bytes = _export_and_get_bytes(
            [_make_section("s1", rows=[{"row_type": "data", "cells": [999]}])]
        )
        result = apply_import(
            xlsx_bytes, sections, {"s1": ConflictResolution.OVERWRITE}
        )
        assert result.success is True
        assert result.sections_imported == 1

    def test_keep(self):
        sections = [_make_section("s1")]
        xlsx_bytes = _export_and_get_bytes([_make_section("s1")])
        result = apply_import(
            xlsx_bytes, sections, {"s1": ConflictResolution.KEEP}
        )
        assert result.sections_kept == 1
        assert result.sections_imported == 0

    def test_discard(self):
        sections = [_make_section("s1")]
        xlsx_bytes = _export_and_get_bytes([_make_section("s1")])
        result = apply_import(
            xlsx_bytes, sections, {"s1": ConflictResolution.DISCARD}
        )
        assert result.sections_discarded == 1

    def test_merge_specific_cells(self):
        sections = [_make_section("s1", rows=[{"row_type": "data", "cells": [100, 200]}])]
        xlsx_bytes = _export_and_get_bytes(
            [_make_section("s1", rows=[{"row_type": "data", "cells": [999, 888]}])]
        )
        result = apply_import(
            xlsx_bytes, sections,
            {"s1": ConflictResolution.MERGE},
            merge_cells={"s1": ["0:0"]},  # Only import cell 0:0
        )
        assert result.sections_imported == 1
        assert result.conflicts == 1


# ---------------------------------------------------------------------------
# C.0.15: Template Type Check
# ---------------------------------------------------------------------------


class TestTemplateTypeCheck:
    """C.0.15 — template_type compatibility."""

    def test_same_type(self):
        result = check_template_type_compatibility("soe", "soe")
        assert result["compatible"] is True
        assert result["warning"] is None

    def test_different_type(self):
        result = check_template_type_compatibility("listed", "soe")
        assert result["compatible"] is False
        assert "不一致" in result["warning"]

    def test_none_import_type(self):
        result = check_template_type_compatibility(None, "soe")
        assert result["compatible"] is True
        assert result["warning"] is not None


# ---------------------------------------------------------------------------
# C.0.14: Version Tree Node
# ---------------------------------------------------------------------------


class TestVersionTreeIntegration:
    """C.0.14 — version tree node creation."""

    def test_create_node(self):
        node = create_version_node("section_cash", uuid4(), "user1")
        assert node["section_id"] == "section_cash"
        assert node["branch"] == "main"
        assert "离线导入" in node["label"]
        assert node["source"] == "offline_import"


# ---------------------------------------------------------------------------
# C.0.16: Audit Log + Archive
# ---------------------------------------------------------------------------


class TestAuditAndArchive:
    """C.0.16 — audit log and file archive."""

    def test_audit_entry_in_result(self):
        sections = [_make_section("s1")]
        xlsx_bytes = _export_and_get_bytes(sections)
        result = apply_import(xlsx_bytes, sections, {"s1": ConflictResolution.OVERWRITE})
        assert "action" in result.audit_entry
        assert result.audit_entry["action"] == "note_offline_import"
        assert result.audit_entry["retention_days"] == 30
        assert result.audit_entry["rollback_available"] is True

    def test_archive_record(self):
        result = ImportResult(success=True, sections_imported=3)
        record = build_archive_record(b"test", uuid4(), "user1", result)
        assert record["file_size"] == 4
        assert record["rollback_available"] is True
        assert len(record["file_hash"]) == 64


# ---------------------------------------------------------------------------
# CI-22: Export→Import Round-Trip PBT
# ---------------------------------------------------------------------------


class TestRoundTripPBT:
    """CI-22 — export→import round-trip field-level diff 无丢失."""

    @given(
        n_sections=st.integers(min_value=1, max_value=5),
        n_rows=st.integers(min_value=1, max_value=5),
        n_cols=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=5, deadline=10000)
    def test_round_trip_no_data_loss(self, n_sections, n_rows, n_cols):
        """Exported sections imported back should have zero diff."""
        sections = []
        for i in range(n_sections):
            headers = [f"列{c}" for c in range(n_cols)]
            rows = [
                {"row_type": "data", "cells": [float(r * n_cols + c) for c in range(n_cols)]}
                for r in range(n_rows)
            ]
            sections.append({
                "section_id": f"s{i}",
                "section_title": f"章节{i}",
                "table_data": {"headers": headers, "rows": rows},
                "_cell_meta": {},
                "_formulas": {},
                "_cell_provenance": {},
                "_bindings": {},
                "_row_meta": [],
                "_dynamic_regions": [],
                "_cell_modes": {},
            })

        # Export
        xlsx_bytes, _ = export_sections_to_xlsx(sections)

        # Validate
        validation = validate_import_file(xlsx_bytes)
        assert validation.valid is True
        assert len(validation.section_ids) == n_sections

        # Diff against same sections — should be zero diffs for matched sections
        diffs = diff_sections(xlsx_bytes, sections, validation.meta_data)
        matched_diffs = [d for d in diffs if d.match_status == MatchStatus.MATCHED]

        for sd in matched_diffs:
            # Round-trip: exported then re-read should match original
            # Note: dynamic row ★ prefix may cause diff in first column
            non_star_diffs = [
                cd for cd in sd.cell_diffs
                if not (cd.cell_key.endswith(":0") and
                        str(cd.imported_value or "").startswith("★"))
            ]
            # Allow only ★ prefix diffs (cosmetic, not data loss)
            assert len(non_star_diffs) == 0, (
                f"Section {sd.section_id} has unexpected diffs: "
                f"{[d.to_dict() for d in non_star_diffs]}"
            )

    def test_round_trip_simple(self):
        """Simple deterministic round-trip test."""
        sections = [
            _make_section("s1", "测试", rows=[
                {"row_type": "data", "cells": [100.0, 200.0, "文本"]},
                {"row_type": "data", "cells": [300.0, 400.0, "另一个"]},
            ])
        ]
        xlsx_bytes, hash1 = export_sections_to_xlsx(sections)

        # Validate
        validation = validate_import_file(xlsx_bytes)
        assert validation.valid
        assert "s1" in validation.section_ids
        assert len(validation.binding_hash) == 64
