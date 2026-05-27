"""CI 卡点：note_template_*.json 必须含合法 row_type + 无空 header.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 0 Task 0.1
Source: scripts/cleanup_note_templates.py（治理脚本写入 row_type）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# 与 scripts/cleanup_note_templates.py 保持一致的合法枚举
VALID_ROW_TYPES = {
    "data",
    "header_label",
    "subtotal",
    "total",
    "dynamic_detail",
    "formula",
}

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_FILES = [
    REPO_ROOT / "backend" / "data" / "note_template_soe.json",
    REPO_ROOT / "backend" / "data" / "note_template_listed.json",
]


def _iter_tables(template: dict):
    """Yield (section_number, table_index, table) for every table in template."""
    for s in template.get("sections", []):
        sec_num = s.get("section_number")
        for ti, tbl in enumerate(s.get("tables") or []):
            yield sec_num, ti, tbl
        for ti, tbl in enumerate(s.get("_tables") or []):
            yield sec_num, ti, tbl


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_template_file_exists(path: Path) -> None:
    assert path.exists(), f"missing template: {path}"


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_headers_have_no_empty_strings(path: Path) -> None:
    """Sprint 0 Task 0.1：headers 中不允许残留空串占位."""
    template = json.loads(path.read_text(encoding="utf-8"))
    offenders: list[tuple] = []
    for sec_num, ti, tbl in _iter_tables(template):
        headers = tbl.get("headers")
        if not isinstance(headers, list):
            continue
        for hi, h in enumerate(headers):
            if h is None or (isinstance(h, str) and not h.strip()):
                offenders.append((sec_num, ti, hi, repr(h)))
    assert not offenders, (
        f"{path.name}: {len(offenders)} empty header placeholders remain "
        f"(first 5: {offenders[:5]})"
    )


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_every_row_has_row_type(path: Path) -> None:
    """Sprint 0 Task 0.1：每个 row 都必须含 row_type."""
    template = json.loads(path.read_text(encoding="utf-8"))
    missing: list[tuple] = []
    for sec_num, ti, tbl in _iter_tables(template):
        for ri, row in enumerate(tbl.get("rows") or []):
            if not isinstance(row, dict):
                continue
            if "row_type" not in row:
                missing.append((sec_num, ti, ri, row.get("label")))
    assert not missing, (
        f"{path.name}: {len(missing)} rows missing row_type "
        f"(first 5: {missing[:5]})"
    )


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_row_type_is_valid_enum(path: Path) -> None:
    """Sprint 0 Task 0.1：row_type 必须 ∈ 合法枚举集合."""
    template = json.loads(path.read_text(encoding="utf-8"))
    invalid: list[tuple] = []
    for sec_num, ti, tbl in _iter_tables(template):
        for ri, row in enumerate(tbl.get("rows") or []):
            if not isinstance(row, dict):
                continue
            rt = row.get("row_type")
            if rt is not None and rt not in VALID_ROW_TYPES:
                invalid.append((sec_num, ti, ri, rt))
    assert not invalid, (
        f"{path.name}: rows with invalid row_type: {invalid[:10]}"
    )


@pytest.mark.parametrize("path", TEMPLATE_FILES, ids=lambda p: p.name)
def test_existing_row_fields_preserved(path: Path) -> None:
    """Sprint 0 Task 0.1：治理脚本不能丢失现有 row 字段（label/values/is_total/...）.

    断言：每个 row 至少有 label（这是治理前就有的最小契约）.
    """
    template = json.loads(path.read_text(encoding="utf-8"))
    no_label: list[tuple] = []
    for sec_num, ti, tbl in _iter_tables(template):
        for ri, row in enumerate(tbl.get("rows") or []):
            if not isinstance(row, dict):
                continue
            if "label" not in row:
                no_label.append((sec_num, ti, ri, list(row.keys())))
    # 允许极少量 label 为空字符串的边界（人工 review），但不能完全没有 label key
    assert not no_label, (
        f"{path.name}: rows missing 'label' key: {no_label[:5]}"
    )
