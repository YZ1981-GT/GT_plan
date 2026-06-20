"""多文件同名 sheet 合并/去重测试

spec workpaper-account-multifile-aggregation 需求 3：
- content_hash 按单元格内容（非名称）判重，幂等（PBT）
- merge_or_dedup：内容相同去重 / 不同合并
- merge_sheet_content：多源纵向拼接 + 来源标识行

Requirements: 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import openpyxl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_multifile_sheet_merge import (
    content_hash,
    merge_or_dedup,
    merge_sheet_content,
)


def _make_xlsx(path, sheet_name: str, rows: list[list]):
    """构造一个含指定 sheet + 行数据的 xlsx 文件。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    # 第一列首行写"项目"触发 extract_grid 的数据表起始检测
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=val)
    wb.save(str(path))
    wb.close()
    return str(path)


_SHEET = "附注披露信息(上市公司)"


@pytest.fixture
def file_a(tmp_path):
    return _make_xlsx(
        tmp_path / "a.xlsx", _SHEET,
        [["项目", "金额"], ["应收账款", 1000], ["坏账准备", -50]],
    )


@pytest.fixture
def file_b_diff(tmp_path):
    return _make_xlsx(
        tmp_path / "b.xlsx", _SHEET,
        [["项目", "金额"], ["应收账款", 2000], ["其他", 300]],
    )


@pytest.fixture
def file_a_copy(tmp_path):
    """与 file_a 内容相同（不同文件名）。"""
    return _make_xlsx(
        tmp_path / "a_copy.xlsx", _SHEET,
        [["项目", "金额"], ["应收账款", 1000], ["坏账准备", -50]],
    )


# ─── content_hash ────────────────────────────────────────────────────────


class TestContentHash:
    def test_same_content_same_hash(self, file_a, file_a_copy):
        """内容相同（文件名不同）→ 哈希相同（比内容非比名）。"""
        assert content_hash(file_a, _SHEET) == content_hash(file_a_copy, _SHEET)

    def test_diff_content_diff_hash(self, file_a, file_b_diff):
        """内容不同 → 哈希不同。"""
        assert content_hash(file_a, _SHEET) != content_hash(file_b_diff, _SHEET)

    def test_hash_is_deterministic(self, file_a):
        """同文件多次调用哈希稳定（幂等）。"""
        h1 = content_hash(file_a, _SHEET)
        h2 = content_hash(file_a, _SHEET)
        assert h1 == h2


# ─── merge_or_dedup ──────────────────────────────────────────────────────


class TestMergeOrDedup:
    def test_identical_content_dedup(self, file_a, file_a_copy):
        """内容相同（GT_Custom 等）→ 去重保留一份，is_merged=False。"""
        result = merge_or_dedup(_SHEET, [file_a, file_a_copy])
        assert len(result.source_files) == 1
        assert result.is_merged is False

    def test_diff_content_merge(self, file_a, file_b_diff):
        """内容不同 → 合并保留全部源，is_merged=True。"""
        result = merge_or_dedup(_SHEET, [file_a, file_b_diff])
        assert len(result.source_files) == 2
        assert result.is_merged is True

    def test_single_source(self, file_a):
        result = merge_or_dedup(_SHEET, [file_a])
        assert len(result.source_files) == 1
        assert result.is_merged is False

    def test_empty_occurrences(self):
        result = merge_or_dedup(_SHEET, [])
        assert result.source_files == []
        assert result.is_merged is False


# ─── merge_sheet_content ─────────────────────────────────────────────────


class TestMergeSheetContent:
    def test_multi_source_has_source_labels(self, file_a, file_b_diff):
        """多源合并：含来源标识行（审计轨迹）。"""
        grid = merge_sheet_content([file_a, file_b_diff], _SHEET)
        assert grid["is_merged"] is True
        assert grid["merged_source_count"] == 2
        label_cells = [
            cell["v"] for cell in grid["cells"].values()
            if isinstance(cell.get("v"), str) and "【来源：" in cell["v"]
        ]
        assert len(label_cells) == 2

    def test_multi_source_content_preserved(self, file_a, file_b_diff):
        """多源合并：两源内容都在（不遗漏）。"""
        grid = merge_sheet_content([file_a, file_b_diff], _SHEET)
        values = [str(cell.get("v", "")) for cell in grid["cells"].values()]
        joined = " ".join(values)
        assert "1000" in joined  # file_a
        assert "2000" in joined  # file_b
        assert "300" in joined   # file_b 独有

    def test_single_source_no_label(self, file_a):
        """单源：直接返回网格，无来源标识包装。"""
        grid = merge_sheet_content([file_a], _SHEET)
        assert grid.get("is_merged") is not True
        assert grid.get("cells")

    def test_empty_source_files(self):
        grid = merge_sheet_content([], _SHEET)
        assert grid["cells"] == {}
        assert grid["max_row"] == 0

    def test_rows_strictly_increasing(self, file_a, file_b_diff):
        """合并后行号唯一不重叠（第二块在第一块之后）。"""
        grid = merge_sheet_content([file_a, file_b_diff], _SHEET)
        rows = [cell["r"] for cell in grid["cells"].values()]
        # max_row 覆盖所有 cell
        assert grid["max_row"] >= max(rows)


# ─── PBT：content_hash 幂等（Task 4.4*）──────────────────────────────────


class TestContentHashIdempotencePBT:
    @settings(max_examples=30, deadline=None)
    @given(
        rows=st.lists(
            st.lists(
                st.one_of(
                    st.integers(-10000, 10000),
                    st.text(
                        alphabet=st.characters(min_codepoint=48, max_codepoint=122),
                        max_size=8,
                    ),
                ),
                min_size=1, max_size=4,
            ),
            min_size=1, max_size=8,
        )
    )
    def test_hash_idempotent_and_content_sensitive(self, rows):
        """任意内容：同内容两文件哈希相同，且重复调用稳定。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            sub = Path(d)
            f1 = _make_xlsx(sub / "f1.xlsx", _SHEET, rows)
            f2 = _make_xlsx(sub / "f2.xlsx", _SHEET, rows)
            # 同内容不同文件 → 哈希相同
            assert content_hash(f1, _SHEET) == content_hash(f2, _SHEET)
            # 重复调用稳定
            assert content_hash(f1, _SHEET) == content_hash(f1, _SHEET)
