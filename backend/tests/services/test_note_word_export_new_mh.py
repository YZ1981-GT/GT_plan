"""新增 multi_header 表的 Word 导出回归。

验证本轮新增的 multi_header 表（P1 列修复后）能被 Word 导出正确消费：
_build_two_level_header_rows 产出的 row0/row1 行数和列跨度正确。

spec: note-template-full-alignment-with-word-authority + consol-comprehensive-runtime-defect-closure
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_tables(std: str) -> list[dict]:
    return json.loads((DATA_DIR / f"consol_note_sections_{std}.json").read_text("utf-8"))


def _tables_with_mh(std: str) -> list[dict]:
    return [t for t in _load_tables(std) if t.get("multi_header") and t.get("_column_groups")]


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_all_mh_tables_have_consistent_column_count(std: str):
    """每张有 multi_header 的表，headers 列数 == multi_header 每行列数 == rows 每行列数。"""
    for t in _tables_with_mh(std):
        n_hdr = len(t["headers"])
        for ri, row in enumerate(t["multi_header"]):
            assert len(row) == n_hdr, (
                f"{std} {t['section_id']} mh[{ri}]: {len(row)} != headers {n_hdr}"
            )
        for ri, row in enumerate(t.get("rows", [])):
            if isinstance(row, list):
                assert len(row) == n_hdr, (
                    f"{std} {t['section_id']} row[{ri}]: {len(row)} != headers {n_hdr}"
                )


@pytest.mark.parametrize("std", ["soe", "listed"])
def test_column_groups_span_within_bounds(std: str):
    """_column_groups 的 start+span 不超出 headers 列数。"""
    for t in _tables_with_mh(std):
        n_hdr = len(t["headers"])
        for cg in t["_column_groups"]:
            end = cg["start"] + cg["span"]
            assert end <= n_hdr, (
                f"{std} {t['section_id']}: cg {cg['group']} end={end} > headers {n_hdr}"
            )


@pytest.mark.parametrize("std,sid", [
    ("soe", "五-5-1"),   # 账龄表（2行mh，P1前就有）
    ("soe", "五-5-2"),   # 坏账分类（3行mh，P1前就有）
    ("soe", "五-17-1"),  # 其他债权投资（P1列修复，8列→8列）
    ("soe", "五-64-1"),  # 未分配利润（P1列修复，5列，有cg）
    ("listed", "五-4-1"), # 应收票据主表（2行mh）
    ("listed", "五-10-1"), # 合同资产（P1列修复，9列→9列）
])
def test_representative_tables_word_header_rows(std: str, sid: str):
    """代表性表的 _column_groups 与 multi_header 产出正确的 Word 两级表头。"""
    from app.services.note_word_exporter import _build_two_level_header_rows

    tables = {t["section_id"]: t for t in _load_tables(std)}
    t = tables[sid]
    headers = t["headers"]
    cg = t["_column_groups"]
    if not cg:
        pytest.skip(f"{std} {sid} 无 _column_groups")

    header_rows = _build_two_level_header_rows(headers, cg)
    assert len(header_rows) == 2, f"应产出 2 行表头，实际 {len(header_rows)}"

    # row0 的 colspan 之和应等于列数
    row0_total = sum(cell["colspan"] for cell in header_rows[0])
    assert row0_total == len(headers), (
        f"{std} {sid}: row0 colspan 之和 {row0_total} != headers {len(headers)}"
    )
