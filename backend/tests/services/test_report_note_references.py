"""Sprint 4 Task 4.3 — report → note 反向溯源端点单测.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 4 Task 4.3
Reqs:   报表 ReportView「附注引用我」侧栏 — rowCode → 附注章节列表

只测纯函数 + 端点 schema（端点本身依赖 PG / 鉴权，集成测试由 e2e 覆盖）。
"""

from __future__ import annotations

import pytest

from app.routers.report_note_references import (
    NoteReference,
    NoteReferencesResponse,
    find_report_references_in_formulas,
)


# ---------------------------------------------------------------------------
# find_report_references_in_formulas 纯函数测试
# ---------------------------------------------------------------------------


def test_find_handles_none_formulas():
    assert find_report_references_in_formulas(None, "BS-001") == set()


def test_find_handles_empty_formulas():
    assert find_report_references_in_formulas({}, "BS-001") == set()


def test_find_handles_empty_row_code():
    formulas = {"0:1": {"expression": "=REPORT('BS-001','current')"}}
    assert find_report_references_in_formulas(formulas, "") == set()


def test_find_handles_non_dict_formulas():
    assert find_report_references_in_formulas("not a dict", "BS-001") == set()  # type: ignore[arg-type]


def test_find_extracts_single_reference():
    formulas = {
        "0:1": {"expression": "=REPORT('BS-001','current')"},
    }
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


def test_find_extracts_multiple_table_indexes():
    """多表章节，不同 table_index 各自命中."""
    formulas = {
        "0:1": {
            "expression": "=REPORT('BS-001','current')",
            "table_index": 0,
        },
        "5:2": {
            "expression": "=REPORT('BS-001','prior')",
            "table_index": 1,
        },
        "9:1": {
            "expression": "=REPORT('BS-002','current')",
            "table_index": 0,
        },
    }
    assert find_report_references_in_formulas(formulas, "BS-001") == {0, 1}


def test_find_supports_double_quotes():
    formulas = {"0:1": {"expression": '=REPORT("BS-001","current")'}}
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


def test_find_supports_legacy_row_function():
    """老语法 ROW('BS-001') 也命中（向后兼容）."""
    formulas = {"0:1": {"expression": "=ROW('BS-001')"}}
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


def test_find_does_not_match_partial():
    """BS-001 不应匹配 BS-0010 / BS-001-x."""
    formulas = {
        "0:1": {"expression": "=REPORT('BS-0010','current')"},
        "1:1": {"expression": "=REPORT('BS-001-x','current')"},
    }
    # BS-001 不应被这两条命中
    assert find_report_references_in_formulas(formulas, "BS-001") == set()


def test_find_skips_malformed_entries():
    formulas = {
        "0:1": "not a dict",
        "1:1": {"expression": None},
        "2:1": {"expression": 123},
        "3:1": {"expression": "=REPORT('BS-001','current')"},
    }
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


def test_find_uses_formula_field_when_expression_missing():
    """兼容 'formula' 字段（部分老 schema）."""
    formulas = {"0:1": {"formula": "=REPORT('BS-001','current')"}}
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


def test_find_normalizes_negative_table_index():
    formulas = {
        "0:1": {
            "expression": "=REPORT('BS-001','current')",
            "table_index": -1,
        },
    }
    # 异常 table_index 归一到 0
    assert find_report_references_in_formulas(formulas, "BS-001") == {0}


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_response_schema_serializes():
    resp = NoteReferencesResponse(
        row_code="BS-001",
        notes=[
            NoteReference(
                note_section="五、1 货币资金",
                section_title="货币资金",
                table_index=0,
            )
        ],
    )
    payload = resp.model_dump()
    assert payload["row_code"] == "BS-001"
    assert len(payload["notes"]) == 1
    assert payload["notes"][0]["note_section"] == "五、1 货币资金"


def test_response_schema_default_empty_notes():
    resp = NoteReferencesResponse(row_code="BS-001")
    assert resp.notes == []
