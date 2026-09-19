"""test_f3_2_notes_source_facts — F3-2 明细表源模板事实固化（openpyxl 直读）

Wave 1 Task 2 of spec `e0-send-list-dedicated-components` (R12.9)。

钉死 `明细表F3-2` 两级表头（含 `是否函证`/`票据保证金比例`/`保证金金额`）、
以及 R9 审计过程第 1 条「承兑保证金……与其他货币资金科目勾稽」原文。
"""
from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

_BACKEND = Path(__file__).resolve().parents[1]
_F3_TEMPLATE = _BACKEND / "wp_templates" / "F" / "F3 应付票据.xlsx"
_F3_2_SHEET = "明细表F3-2"

# 两级表头 R13 一级 + R14 二级
_R13_EXPECTED = {
    "A": "票据号",
    "B": "票据类别",
    "C": "关联方类型",
    "D": "票据关系人",
    "G": "票据期限",
    "J": "票面利率",
    "K": "是否承兑",
    "L": "期初余额",
    "M": "本期开票",
    "N": "本期承兑",
    "O": "期末未审数",
    "P": "账项调整",
    "Q": "重分类调整",
    "R": "期末审定数",
    "S": "已计利息",
    "T": "是否函证",
    "U": "票据保证金比例",
    "V": "保证金金额",
    "W": "备注",
}

_R14_EXPECTED = {
    "D": "出票人",
    "E": "承兑人",
    "F": "收款人",
    "G": "出票日",
    "H": "到期日",
    "I": "期限",
}

# R9 审计过程关键原文
_R9_KEY_PHRASES = [
    "承兑保证金",
    "其他货币资金科目勾稽",
]


@pytest.fixture(scope="module")
def f3_workbook():
    lock = _F3_TEMPLATE.parent / f"~${_F3_TEMPLATE.name}"
    if lock.exists():
        pytest.skip(f"源模板被锁定：{lock}")
    if not _F3_TEMPLATE.exists():
        pytest.skip(f"真实模板缺失：{_F3_TEMPLATE}")
    wb = openpyxl.load_workbook(str(_F3_TEMPLATE), data_only=False)
    yield wb
    wb.close()


def test_f3_2_sheet_exists(f3_workbook):
    assert _F3_2_SHEET in f3_workbook.sheetnames


def test_f3_2_r13_first_level_headers(f3_workbook):
    """R13 一级表头逐字验证（含 `是否函证`/`票据保证金比例`/`保证金金额`）。"""
    ws = f3_workbook[_F3_2_SHEET]
    for col_letter, expected_label in _R13_EXPECTED.items():
        col_idx = openpyxl.utils.column_index_from_string(col_letter)
        actual = ws.cell(row=13, column=col_idx).value
        assert actual == expected_label, (
            f"F3-2 R13.{col_letter} 应为 {expected_label!r}，实为 {actual!r}"
        )


def test_f3_2_r14_second_level_headers(f3_workbook):
    """R14 二级表头逐字验证。"""
    ws = f3_workbook[_F3_2_SHEET]
    for col_letter, expected_label in _R14_EXPECTED.items():
        col_idx = openpyxl.utils.column_index_from_string(col_letter)
        actual = ws.cell(row=14, column=col_idx).value
        assert actual == expected_label, (
            f"F3-2 R14.{col_letter} 应为 {expected_label!r}，实为 {actual!r}"
        )


def test_f3_2_total_columns_is_19(f3_workbook):
    """R13 表头共 19 列有值（A~W 跳过合并区 = 19 个独立标签）。"""
    ws = f3_workbook[_F3_2_SHEET]
    # 数 R13 中有值的列（含合并区只算首格）
    count = 0
    for c in range(1, 30):
        if ws.cell(row=13, column=c).value is not None:
            count += 1
    assert count == 19, f"F3-2 R13 有值列数应为 19，实为 {count}"


def test_f3_2_r9_contains_audit_procedure(f3_workbook):
    """R9 审计过程第 1 条含「承兑保证金……与其他货币资金科目勾稽」。"""
    ws = f3_workbook[_F3_2_SHEET]
    r9_text = str(ws.cell(row=9, column=1).value or "")
    for phrase in _R9_KEY_PHRASES:
        assert phrase in r9_text, f"F3-2 R9 应含 {phrase!r}，实为 {r9_text[:80]!r}…"


def test_f3_2_is_confirm_column_is_at_t(f3_workbook):
    """「是否函证」列在 T 列（第 20 列），这是 E0-5 上游筛选的落点。"""
    ws = f3_workbook[_F3_2_SHEET]
    t13 = ws.cell(row=13, column=20).value
    assert t13 == "是否函证", f"F3-2 R13.T 应为「是否函证」，实为 {t13!r}"


# ─── 反向自检 ────────────────────────────────────────────────────────────────

def test_reverse_check_removing_is_confirm_from_expected_would_be_detected():
    """反向自检：如果有人把「是否函证」从 F3-2 列集移除的判断复活，本组守卫要能检测出。"""
    # 「是否函证」确实在 R13 期望列集里
    assert "T" in _R13_EXPECTED
    assert _R13_EXPECTED["T"] == "是否函证"
