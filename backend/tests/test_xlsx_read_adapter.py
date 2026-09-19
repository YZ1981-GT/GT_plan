"""xlsx_read_adapter 单测。

覆盖：
- calamine=True vs False 归一化输出等价
- calamine 不可用时降级 openpyxl
- XLSX_READ_USE_CALAMINE=False 走 openpyxl
- sheet_name=None 取第一个表 / 多 sheet 指定名 / sheet 不存在行为
- list_sheet_names
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest


def _build_xlsx(tmp_path: Path, sheets: dict[str, list[list]], filename: str = "test.xlsx") -> Path:
    """构造含指定 sheets 的 xlsx fixture。"""
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = name
            first = False
        else:
            ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    path = tmp_path / filename
    wb.save(str(path))
    return path


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    """多 sheet xlsx，含空字符串 cell 验证归一化。"""
    return _build_xlsx(
        tmp_path,
        {
            "Data": [["name", "value", None], [None, 42, "hello"]],
            "Second": [["x", "y"], [1, 2]],
        },
    )


# ─── Task 3: calamine vs openpyxl 输出等价 ───


def _normalize_for_comparison(rows: list[list]) -> list[list]:
    """归一化比较辅助：int/float 容忍（42==42.0），剔除全 None 尾行。"""
    # 剔除尾部全空行（calamine 不返回 trailing empty rows）
    while rows and all(c is None for c in rows[-1]):
        rows = rows[:-1]
    result = []
    for row in rows:
        normalized = []
        for c in row:
            # calamine 数字全返 float，openpyxl 保留 int — 容忍
            if isinstance(c, float) and c == int(c):
                normalized.append(int(c))
            else:
                normalized.append(c)
        result.append(normalized)
    return result


def test_calamine_vs_openpyxl_equivalent(sample_xlsx: Path):
    """calamine=True vs False 归一化后输出一致（容忍 int/float + trailing empty rows）。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    rows_cal = read_sheet_values(sample_xlsx, "Data", prefer_calamine=True)
    rows_opy = read_sheet_values(sample_xlsx, "Data", prefer_calamine=False)
    assert _normalize_for_comparison(rows_cal) == _normalize_for_comparison(rows_opy)


def test_normalization_empty_string_to_none(tmp_path: Path):
    """calamine 的 "" → None 归一化与 openpyxl 空 cell=None 对齐。"""
    from app.services.xlsx_read_adapter import _normalize_rows

    # calamine 返回 "" 表示空 cell，归一化后应变 None
    raw = [["a", "", "b"], ["", None, ""]]
    normalized = _normalize_rows(raw)
    assert normalized == [["a", None, "b"], [None, None, None]]


# ─── Task 3: calamine 不可用时降级 openpyxl ───


def test_fallback_when_calamine_unavailable(sample_xlsx: Path):
    """monkeypatch _calamine_available → False 时降级 openpyxl。"""
    from app.services import xlsx_read_adapter
    from app.services.xlsx_read_adapter import read_sheet_values

    with patch.object(xlsx_read_adapter, "_calamine_available", return_value=False):
        rows = read_sheet_values(sample_xlsx, "Data", prefer_calamine=True)
    # 应能正常读取（openpyxl fallback）
    assert len(rows) == 2
    assert rows[1][1] == 42


# ─── Task 3: XLSX_READ_USE_CALAMINE=False 走 openpyxl ───


def test_setting_disabled_forces_openpyxl(sample_xlsx: Path):
    """XLSX_READ_USE_CALAMINE=False 时即使 prefer_calamine=True 也走 openpyxl。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    with patch("app.services.xlsx_read_adapter.settings") as mock_settings:
        mock_settings.XLSX_READ_USE_CALAMINE = False
        rows = read_sheet_values(sample_xlsx, "Data", prefer_calamine=True)
    assert len(rows) == 2


# ─── Task 3: sheet_name 行为 ───


def test_sheet_name_none_reads_first_sheet(sample_xlsx: Path):
    """sheet_name=None 取第一个表（Data）。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    rows = read_sheet_values(sample_xlsx, sheet_name=None)
    # first sheet is "Data" with 2 rows
    assert len(rows) == 2
    assert rows[0][0] == "name"


def test_sheet_name_specific(sample_xlsx: Path):
    """指定 sheet 名读取对应内容。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    rows = read_sheet_values(sample_xlsx, "Second")
    assert len(rows) == 2
    assert rows[0] == ["x", "y"]
    assert rows[1] == [1, 2]


def test_nonexistent_sheet_returns_empty(sample_xlsx: Path):
    """不存在的 sheet 名返回空列表（不抛异常）。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    rows = read_sheet_values(sample_xlsx, "NoSuchSheet")
    assert rows == []


# ─── list_sheet_names ───


def test_list_sheet_names(sample_xlsx: Path):
    """list_sheet_names 返回所有 sheet 名称。"""
    from app.services.xlsx_read_adapter import list_sheet_names

    names = list_sheet_names(sample_xlsx)
    assert names == ["Data", "Second"]


def test_list_sheet_names_nonexistent_file(tmp_path: Path):
    """不存在的文件返回空列表。"""
    from app.services.xlsx_read_adapter import list_sheet_names

    names = list_sheet_names(tmp_path / "nope.xlsx")
    assert names == []


# ─── 边界条件 ───


def test_empty_file_returns_empty(tmp_path: Path):
    """空文件（0 字节）返回空列表。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    path = tmp_path / "empty.xlsx"
    path.write_bytes(b"")
    assert read_sheet_values(path) == []


def test_nonexistent_path_returns_empty(tmp_path: Path):
    """不存在的路径返回空列表。"""
    from app.services.xlsx_read_adapter import read_sheet_values

    assert read_sheet_values(tmp_path / "nope.xlsx") == []
