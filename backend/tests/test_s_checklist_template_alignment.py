"""Offline D4.4 checks for S-checklist component/template alignment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

pytest.importorskip("openpyxl")
pytest.importorskip("xlrd")

from scripts.analyze.check_s_checklist_template_alignment import (  # noqa: E402
    build_report,
)


def _entry(report: dict, component_type: str) -> dict:
    return next(item for item in report["entries"] if item["component_type"] == component_type)


def _sheet(entry: dict, sheet_name: str) -> dict:
    return next(sheet for sheet in entry["sheets"] if sheet["sheet_name"] == sheet_name)


def _difference_kinds(sheet: dict) -> set[str]:
    return {difference["kind"] for difference in sheet["differences"]}


def test_real_templates_use_format_specific_readers_and_cover_all_12_components() -> None:
    report = build_report()

    assert report["read_only"] is True
    assert report["format_routing"] == {".xlsx": "openpyxl", ".xls": "xlrd"}
    assert report["component_count"] == 12
    assert len(set(report["component_types"])) == 12
    assert all(entry["status"] != "missing_workbook" for entry in report["entries"])
    assert all(
        sheet["status"] == "ok"
        for entry in report["entries"]
        for sheet in entry.get("sheets", [])
    )

    xlsx_entries = [entry for entry in report["entries"] if entry["format"] == "xlsx"]
    xls_entries = [entry for entry in report["entries"] if entry["format"] == "xls"]
    assert xlsx_entries
    assert {entry["reader"] for entry in xlsx_entries} == {"openpyxl"}
    assert {entry["reader"] for entry in xls_entries} == {"xlrd"}
    assert {entry["component_type"] for entry in xls_entries} == {
        "s17-nonrecurring-detail",
        "s17-reconciliation",
        "s17-tax-impact",
    }
    assert all(
        entry["workbook"].lower().endswith(".xls")
        for entry in xls_entries
    )


def test_s17_xls_headers_and_differences_are_recorded_without_xlsx_fallback() -> None:
    report = build_report()
    detail = _entry(report, "s17-nonrecurring-detail")
    s17_1 = _sheet(detail, "审定表S17-1")
    s17_2 = _sheet(detail, "审核表（合并）S17-2")
    s17_3 = _sheet(detail, "审核表（个别报表）S17-3")

    assert {s17_1["reader"], s17_2["reader"], s17_3["reader"]} == {"xlrd"}
    assert s17_1["header_rows"] == [5, 6]
    assert s17_1["template_columns"] == [
        "项目",
        "本年度",
        "上年度",
        "说明",
        "未审数",
        "审计调整",
        "审定数",
    ]
    assert {
        field["field"] for field in s17_1["matched_fields"]
    } >= {"itemName", "currentAmount", "priorAmount"}
    assert {"taxImpact", "netAmount"} <= {
        difference["field"]
        for difference in s17_1["differences"]
        if difference["kind"] == "ui_field_missing_in_template_header"
    }
    assert {"说明", "未审数", "审计调整", "审定数"} <= {
        difference["template_label"]
        for difference in s17_1["differences"]
        if difference["kind"] == "template_column_not_consumed_by_ui"
    }

    assert s17_2["header_rows"] == [5]
    assert s17_2["reader"] == "xlrd"
    assert "合并金额" in s17_2["template_columns"]
    assert s17_3["header_rows"] == [5]
    assert s17_3["matched_fields"]
    assert any(
        difference["field"] == "source"
        for difference in s17_3["differences"]
        if difference["kind"] == "ui_field_missing_in_template_header"
    )


def test_xlsx_table_headers_and_freeform_differences_are_distinguished() -> None:
    report = build_report()

    s9_control = _sheet(_entry(report, "s9-internal-control"), "内部控制调查表S9-2")
    assert s9_control["reader"] == "openpyxl"
    assert s9_control["header_rows"] == [6, 7]
    assert s9_control["template_columns"] == [
        "调查问题",
        "答案",
        "是",
        "弱",
        "否",
        "不适用",
    ]
    assert "evidence" in {
        difference["field"]
        for difference in s9_control["differences"]
        if difference["kind"] == "ui_field_missing_in_template_header"
    }
    assert "indexRef" in {
        difference["field"]
        for difference in s9_control["differences"]
        if difference["kind"] == "ui_field_missing_in_template_header"
    }

    s1 = _sheet(_entry(report, "s1-regulation-record"), "S1-1对法律法规的考虑记录表")
    assert s1["reader"] == "openpyxl"
    assert s1["comparison"] == "freeform_template_vs_grid_component"
    assert s1["header_rows"] == []
    assert "ui_field_missing_in_template_header" in _difference_kinds(s1)

    s9_reference = _sheet(_entry(report, "s9-legal-regulations"), "电子商务法律法规")
    assert s9_reference["comparison"] == "readonly_reference"
    assert s9_reference["ui_columns"] == []
    assert s9_reference["differences"] == []


def test_alignment_report_is_json_serializable_and_deterministic() -> None:
    first = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    second = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    assert first == second
