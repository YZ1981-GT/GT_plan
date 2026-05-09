"""S6-12: xlsx 合并单元格 forward-fill 测试。

典型场景：银行存款 4 行，只在第 1 行显示 account_code，后续 3 行为 None。
forward-fill 后 account_code 应从第 1 行继承到后续 3 行。
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from app.services.ledger_import.parsers.excel_parser import iter_excel_rows


def _make_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_no_forward_fill_keeps_none():
    """不启用 forward-fill 时，空值保持 None。"""
    data = [
        ["科目编码", "凭证号", "借方"],
        ["1002", "记-1", 100],
        [None, "记-2", 200],  # 合并单元格典型：None
        [None, "记-3", 300],
    ]
    content = _make_xlsx(data)
    all_rows = []
    for chunk in iter_excel_rows(content, "Sheet1", data_start_row=1):
        all_rows.extend(chunk)

    assert len(all_rows) == 3
    assert all_rows[1][0] is None
    assert all_rows[2][0] is None


def test_forward_fill_propagates_value():
    """启用 forward-fill 后，空值被上一行非空值填充。"""
    data = [
        ["科目编码", "凭证号", "借方"],
        ["1002", "记-1", 100],
        [None, "记-2", 200],
        [None, "记-3", 300],
        ["4103", "记-4", 400],
        [None, "记-5", 500],
    ]
    content = _make_xlsx(data)
    all_rows = []
    for chunk in iter_excel_rows(
        content, "Sheet1", data_start_row=1, forward_fill_cols=[0],
    ):
        all_rows.extend(chunk)

    assert len(all_rows) == 5
    assert all_rows[0][0] == "1002"
    assert all_rows[1][0] == "1002"  # 填充
    assert all_rows[2][0] == "1002"  # 填充
    assert all_rows[3][0] == "4103"  # 重置
    assert all_rows[4][0] == "4103"  # 继续填充


def test_forward_fill_multiple_cols():
    """多列同时 forward-fill。"""
    data = [
        ["科目编码", "科目名称", "借方"],
        ["1002", "银行存款", 100],
        [None, None, 200],
        [None, None, 300],
    ]
    content = _make_xlsx(data)
    all_rows = []
    for chunk in iter_excel_rows(
        content, "Sheet1", data_start_row=1, forward_fill_cols=[0, 1],
    ):
        all_rows.extend(chunk)

    assert all_rows[1][0] == "1002"
    assert all_rows[1][1] == "银行存款"
    assert all_rows[2][0] == "1002"
    assert all_rows[2][1] == "银行存款"


def test_forward_fill_empty_string_treated_as_empty():
    """空串和 None 一样被视为需要填充。"""
    data = [
        ["col"],
        ["value1"],
        [""],
        ["  "],  # 纯空白
        ["value2"],
    ]
    content = _make_xlsx(data)
    all_rows = []
    for chunk in iter_excel_rows(
        content, "Sheet1", data_start_row=1, forward_fill_cols=[0],
    ):
        all_rows.extend(chunk)

    assert all_rows[0][0] == "value1"
    assert all_rows[1][0] == "value1"  # 空串 → 填充
    assert all_rows[2][0] == "value1"  # 纯空白 → 填充
    assert all_rows[3][0] == "value2"


def test_forward_fill_first_row_none_remains_none():
    """首行就是 None 时无法填充，保持 None。"""
    data = [
        ["col"],
        [None],
        ["value1"],
        [None],
    ]
    content = _make_xlsx(data)
    all_rows = []
    for chunk in iter_excel_rows(
        content, "Sheet1", data_start_row=1, forward_fill_cols=[0],
    ):
        all_rows.extend(chunk)

    assert all_rows[0][0] is None  # 无上一行可填
    assert all_rows[1][0] == "value1"
    assert all_rows[2][0] == "value1"  # 从第 2 行填
