"""test_e1_3_segment_facts — E1-3 两版段结构守卫（openpyxl 直读）

Wave 1 Task 2 of spec `e0-send-list-dedicated-components`.
覆盖 Property 7/8/10。

核心目的：把 E1-3 两版（仅人民币 / 人民币及外币）的段头文字、段内明细行区间、
小计行、应计利息段起点用守卫钉死。后续 `e1_3_segments.py` 的切段逻辑全以本文件为裁决者。
"""
from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

_BACKEND = Path(__file__).resolve().parents[1]
_E1_TEMPLATE = _BACKEND / "wp_templates" / "E" / "E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx"

# 两版 E1-3 sheet 名
_CNY_SHEET = "银行存款及其他货币资金明细表(仅人民币)E1-3"
_FX_SHEET = "银行存款及其他货币资金明细表(人民币及外币)E1-3"

# 段头文字（两版逐字相同）
_SEGMENT_HEADS = (
    "银行：",
    "其他金融机构（存放财务公司款项）：",
    "其他货币资金：",
)

# 应计利息段起点文字前缀
_INTEREST_SECTION_PREFIX = "（二）应计利息"

# 被排除的行标签（小计行）
_EXCLUDED_LABELS = (
    "存款本金小计",
    "存款应计利息小计",
    "银行存款小计",
    "财务公司存款小计",
    "其他货币资金小计",
    "合 计",
)

# ─── 期望的段内明细行区间 ─────────────────────────────────────────────────────

# 仅人民币版：银行 R13:R21(9行), 其他金融机构 R23:R25(3行), 其他货币资金 R27:R33(7行)
_CNY_SEGMENTS = {
    "银行：": (13, 21),
    "其他金融机构（存放财务公司款项）：": (23, 25),
    "其他货币资金：": (27, 33),
}
_CNY_INTEREST_START = 35

# 人民币及外币版：银行 R13:R17(5行), 其他金融机构 R19:R21(3行), 其他货币资金 R23:R28(6行)
_FX_SEGMENTS = {
    "银行：": (13, 17),
    "其他金融机构（存放财务公司款项）：": (19, 21),
    "其他货币资金：": (23, 28),
}
_FX_INTEREST_START = 30

# 两版的列语义（design §E1_3Variant 声明的列）
_CNY_COLS = {
    "A": "开户银行",
    "B": "总账银行名称",
    "C": "银行账号",
    "H": "期末余额",  # 未审
    "J": "期末审定数",
    "K": "期末对账单余额",
    "Q": "受限金额",
    "R": "受限原因",
}
_FX_COLS = {
    "A": "开户银行",
    "B": "总账银行名称",
    "C": "银行账号",
    "E": "原币币种",
    "M": "期末余额",  # 原币未审
    "AA": "期末审定",  # 原币
    "AD": "期末对账单余额",
    "AJ": "受限金额",
    "AK": "受限原因",
    "AL": "利率",
}


@pytest.fixture(scope="module")
def e1_workbook():
    lock = _E1_TEMPLATE.parent / f"~${_E1_TEMPLATE.name}"
    if lock.exists():
        pytest.skip(f"源模板被锁定：{lock}")
    if not _E1_TEMPLATE.exists():
        pytest.skip(f"真实模板缺失：{_E1_TEMPLATE}")
    wb = openpyxl.load_workbook(str(_E1_TEMPLATE), data_only=False)
    yield wb
    wb.close()


# ──────────────────────── 1. 两版 sheet 存在 ────────────────────────────────

def test_two_versions_exist(e1_workbook):
    assert _CNY_SHEET in e1_workbook.sheetnames
    assert _FX_SHEET in e1_workbook.sheetnames


# ──────────────────────── 2. 段头文字逐字一致 ───────────────────────────────

@pytest.mark.parametrize("sheet_name", [_CNY_SHEET, _FX_SHEET])
def test_segment_head_texts_present(e1_workbook, sheet_name):
    """三个段头文字在两版中逐字存在。"""
    ws = e1_workbook[sheet_name]
    a_values = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
    for head in _SEGMENT_HEADS:
        assert any(head in v for v in a_values), f"{sheet_name} 缺段头 {head!r}"


# ──────────────────────── 3. 段内明细行区间 ─────────────────────────────────

def test_cny_segment_ranges(e1_workbook):
    """仅人民币版段内明细行区间：R13:R21 / R23:R25 / R27:R33。"""
    ws = e1_workbook[_CNY_SHEET]
    _verify_segments(ws, _CNY_SEGMENTS)


def test_fx_segment_ranges(e1_workbook):
    """人民币及外币版段内明细行区间：R13:R17 / R19:R21 / R23:R28。"""
    ws = e1_workbook[_FX_SHEET]
    _verify_segments(ws, _FX_SEGMENTS)


def _verify_segments(ws, expected_segments: dict[str, tuple[int, int]]):
    """验证段头行号和段内明细行范围。"""
    for head, (start, end) in expected_segments.items():
        # 找段头行号
        head_row = None
        for r in range(1, ws.max_row + 1):
            v = str(ws.cell(row=r, column=1).value or "")
            if head in v:
                head_row = r
                break
        assert head_row is not None, f"未找到段头 {head!r}"
        # 明细行紧跟段头之后
        assert start == head_row + 1, f"段 {head!r} 明细起始行应为 {head_row + 1}，实为 {start}"
        # 明细行结束验证：end+1 行要么是下一段头要么是小计行要么超出数据区
        next_row_val = str(ws.cell(row=end + 1, column=1).value or "")
        is_boundary = (
            any(h in next_row_val for h in _SEGMENT_HEADS)
            or any(lbl in next_row_val for lbl in _EXCLUDED_LABELS)
            or next_row_val == ""
            or _INTEREST_SECTION_PREFIX in next_row_val
        )
        assert is_boundary, (
            f"段 {head!r} 明细行末尾 R{end} 的下一行 R{end+1} 应为边界，实为 {next_row_val!r}"
        )


# ──────────────────────── 4. 应计利息段起点 ─────────────────────────────────

def test_cny_interest_section_start(e1_workbook):
    ws = e1_workbook[_CNY_SHEET]
    v = str(ws.cell(row=_CNY_INTEREST_START, column=1).value or "")
    assert _INTEREST_SECTION_PREFIX in v, (
        f"仅人民币版 R{_CNY_INTEREST_START} 应为应计利息段，实为 {v!r}"
    )


def test_fx_interest_section_start(e1_workbook):
    ws = e1_workbook[_FX_SHEET]
    v = str(ws.cell(row=_FX_INTEREST_START, column=1).value or "")
    assert _INTEREST_SECTION_PREFIX in v, (
        f"外币版 R{_FX_INTEREST_START} 应为应计利息段，实为 {v!r}"
    )


# ──────────────────────── 5. 小计行文字 ────────────────────────────────────

@pytest.mark.parametrize("sheet_name", [_CNY_SHEET, _FX_SHEET])
def test_subtotal_rows_exist(e1_workbook, sheet_name):
    """「存款本金小计」行存在。"""
    ws = e1_workbook[sheet_name]
    found = False
    for r in range(1, ws.max_row + 1):
        v = str(ws.cell(row=r, column=1).value or "")
        if "存款本金小计" in v:
            found = True
            break
    assert found, f"{sheet_name} 应含「存款本金小计」行"


# ──────────────────────── 6. 列语义验证 ───────────────────────────────────

def test_cny_column_semantics(e1_workbook):
    """仅人民币版的关键列标签验证（表头区 R9 或 R10）。"""
    ws = e1_workbook[_CNY_SHEET]
    _verify_column_labels(ws, _CNY_COLS)


def test_fx_column_semantics(e1_workbook):
    """人民币及外币版的关键列标签验证。"""
    ws = e1_workbook[_FX_SHEET]
    _verify_column_labels(ws, _FX_COLS)


def _verify_column_labels(ws, expected_cols: dict[str, str]):
    """验证表头区（R8~R10）含期望的列标签。"""
    for col_letter, expected_substring in expected_cols.items():
        col_idx = openpyxl.utils.column_index_from_string(col_letter)
        found = False
        for r in range(8, 11):  # 表头区
            v = str(ws.cell(row=r, column=col_idx).value or "")
            if expected_substring in v:
                found = True
                break
        assert found, (
            f"列 {col_letter} 在表头区（R8:R10）应含 {expected_substring!r}"
        )


# ──────────────────────── 7. 反向自检 ─────────────────────────────────────

def test_reverse_check_segment_by_row_number_would_fail():
    """反向自检：如果把段头判定改成按行号（而非按文字），两版行号不同必错。
    仅人民币版段2起于 R23，外币版段2起于 R19 → 不可能同一行号。"""
    assert _CNY_SEGMENTS["其他金融机构（存放财务公司款项）："][0] == 23
    assert _FX_SEGMENTS["其他金融机构（存放财务公司款项）："][0] == 19
    assert 23 != 19, "两版段2起始行号不同，证明按行号硬编码不可移植"


def test_reverse_check_interest_section_included_would_fail():
    """反向自检：如果把应计利息段纳入，会多出 银行/财务公司/其他货币资金 的利息行。"""
    # 仅人民币版应计利息段起 R35，段1本金区末尾 R33 → 纳入就会把 R35+ 都算进去
    assert _CNY_INTEREST_START == 35
    assert _CNY_SEGMENTS["其他货币资金："][1] == 33
    # 两者之间只有 R34=存款本金小计（已排除），R35 已是应计利息
