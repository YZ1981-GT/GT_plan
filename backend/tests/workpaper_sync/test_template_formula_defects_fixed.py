# -*- coding: utf-8 -*-
"""权威模板公式修正守卫（spec oo-writeback-template-parity-closure R1 / R10.1）。

修复清单只有一份：`scripts/fix/fix_template_formula_defects.fixes()`（逐格核实依据见 spec design §2）。
本守卫直接读那份清单，断言清单内每一格在 `backend/wp_templates/` 里已是修正后的值：
换回旧模板、重新导入旧字节、或有人手工改回某一格，这里立刻红，并点名是哪一格。

只读需要的 sheet / 行（read_only 逐行扫一遍），不做整册快照。
"""
from __future__ import annotations

import io
import warnings
from collections import defaultdict
from pathlib import Path

import openpyxl
import pytest
from openpyxl.utils.cell import coordinate_from_string

from scripts.fix.fix_template_formula_defects import TEMPLATES, Fix, fixes, patch_bytes

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

_FIXES = fixes()
_BOOKS = sorted({f.template for f in _FIXES})


def _read_cells(data: bytes, wanted: dict[str, set[str]]) -> dict[tuple[str, str], object]:
    """{sheet: {coord}} → {(sheet, coord): openpyxl 读到的值}；只扫这些 sheet 涉及的行段。"""
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    try:
        out: dict[tuple[str, str], object] = {}
        for sheet, coords in wanted.items():
            ws = wb[sheet]
            rows = [coordinate_from_string(c)[1] for c in coords]
            for row in ws.iter_rows(min_row=min(rows), max_row=max(rows)):
                for cell in row:
                    coord = getattr(cell, "coordinate", None)
                    if coord in coords:
                        out[(sheet, coord)] = cell.value
        return out
    finally:
        wb.close()


def _off_list(template: str, data: bytes) -> list[str]:
    items = [f for f in _FIXES if f.template == template]
    wanted: dict[str, set[str]] = defaultdict(set)
    for f in items:
        wanted[f.sheet].add(f.coord)
    got = _read_cells(data, wanted)
    return [
        f"{f.sheet}!{f.coord} 实得 {got.get((f.sheet, f.coord))!r}，应为 {f.new!r}"
        for f in items
        if got.get((f.sheet, f.coord)) != f.new
    ]


def test_fix_list_is_non_trivial() -> None:
    """清单为空时参数化测试不会收集；数量棘轮防止整批清单被误删。"""
    assert len(_BOOKS) >= 27 and len(_FIXES) >= 386, (len(_BOOKS), len(_FIXES))


def test_n5_fourth_batch_cells_are_explicitly_in_the_fix_list() -> None:
    required = {
        ("N/N5 所得税费用.xlsx", "加计扣除研发费用情况明细表N5-6-1", "D11"),
        ("N/N5 所得税费用.xlsx", "加计扣除研发费用情况明细表N5-6-1", "E12"),
        ("N/N5 所得税费用.xlsx", "递延所得税费用核对表N5-8", "H12"),
    }
    actual = {(fix.template, fix.sheet, fix.coord) for fix in _FIXES}
    assert required <= actual


@pytest.mark.parametrize("template", _BOOKS)
def test_every_listed_cell_is_fixed_in_the_authoritative_template(template: str) -> None:
    off = _off_list(template, (TEMPLATES / template).read_bytes())
    assert not off, f"{template} 有 {len(off)} 格不是修正后的值：\n  " + "\n  ".join(off[:10])


def test_mutation_reverting_one_cell_is_reported() -> None:
    """变异：把 N4-2!E9 改回修复前的 `=B9+C9+N4`（整册其余字节不动），判据必须点名这一格。"""
    target = next(f for f in _FIXES if f.coord == "E9" and f.sheet == "税金及附加明细表N4-2")
    assert target.old is not None
    data = (TEMPLATES / target.template).read_bytes()
    reverted = patch_bytes(data, [Fix(target.template, target.sheet, target.coord, target.new, target.old)])
    off = _off_list(target.template, reverted)
    assert off == [f"{target.sheet}!E9 实得 {target.old!r}，应为 {target.new!r}"], off


def test_mutation_putting_back_a_cleared_formula_is_reported() -> None:
    """变异：D1-15 ④ 是清掉公式的录入格，有人把 `=B14-D14` 补回去，判据必须点名这一格（new=None 分支）。"""
    target = next(f for f in _FIXES if f.coord == "E14" and f.sheet == "应收票据坏账准备测试表D1-15")
    assert target.new is None and target.old == "=B14-D14"
    data = (TEMPLATES / target.template).read_bytes()
    reverted = patch_bytes(data, [Fix(target.template, target.sheet, target.coord, None, target.old)])
    off = _off_list(target.template, reverted)
    assert off == [f"{target.sheet}!E14 实得 {target.old!r}，应为 None"], off


def test_templates_root_is_the_runtime_authority() -> None:
    assert TEMPLATES == Path(__file__).resolve().parents[2] / "wp_templates"
