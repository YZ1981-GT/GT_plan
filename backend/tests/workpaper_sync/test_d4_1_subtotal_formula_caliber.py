# -*- coding: utf-8 -*-
"""P16 判据：D4-1 小计口径以**模板公式为第三边**（需求 7.1）。

spec: d4-html-to-oo-store-contract-alignment · Task 16
Requirements 7.1 · Property 16

═══ 为什么以模板为第三边 ═══

前端 buildSubtotalRow 的本期 AJE/RJE 小计原取 D4-4 汇总额、不逐行汇总，与 Excel 公式口径
不同 ⇒ 两侧小计可能不等且无告警。Task 16 把前端改为逐行汇总。本判据锁死"逐行汇总"是与
Excel 一致的那一侧——直接读权威模板 `D4 收入底稿.xlsx` 的 C12/D12/E12/R18/R19 真实公式，
断言小计行是 `=SUM(数据行区间)` 逐行汇总形态。

🔴 不拿"前端 vs OO"互比：两侧同错会自洽（I 循环踩过 38 张列契约全绿而行维度从没比过的
同型陷阱）。模板 xlsx 是独立第三边。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_d4_adjudication_sheet as A  # noqa: E402

TEMPLATE = _BACKEND / "wp_templates" / A.TEMPLATE_RELATIVE_PATH
SHEET = A.MANAGED_SHEET_D41


@pytest.fixture(scope="module")
def formulas() -> dict[str, str]:
    wb = openpyxl.load_workbook(TEMPLATE, data_only=False)
    ws = wb[SHEET]
    out: dict[str, str] = {}
    for row in (A.SUBTOTAL_ROW_MAIN, A.SUBTOTAL_ROW_OTHER, A.TOTAL_ROW_D41):
        for col in "BCDEFGHI":
            v = ws[f"{col}{row}"].value
            if isinstance(v, str):
                out[f"{col}{row}"] = v
    wb.close()
    return out


def test_main_subtotal_current_aje_rje_are_row_sum(formulas: dict[str, str]) -> None:
    """主营小计本期 AJE(C12)/RJE(D12) 是逐行 SUM（= 前端应对齐的口径）。"""
    r = A.SUBTOTAL_ROW_MAIN  # 12
    first, last = A.FIRST_DATA_ROW_MAIN, A.LAST_DATA_ROW_MAIN  # 8, 11
    assert formulas.get(f"C{r}") == f"=SUM(C{first}:C{last})", (
        f"C{r} 本期账项调整小计应为逐行 SUM，实得 {formulas.get(f'C{r}')!r}"
    )
    assert formulas.get(f"D{r}") == f"=SUM(D{first}:D{last})", (
        f"D{r} 本期重分类调整小计应为逐行 SUM，实得 {formulas.get(f'D{r}')!r}"
    )
    # 未审数同样逐行 SUM（对照，确认整列口径一致）。
    assert formulas.get(f"B{r}") == f"=SUM(B{first}:B{last})"


def test_other_subtotal_current_aje_rje_are_row_sum(formulas: dict[str, str]) -> None:
    """其他小计本期 AJE(C18)/RJE(D18) 逐行 SUM。"""
    r = A.SUBTOTAL_ROW_OTHER  # 18
    first, last = A.FIRST_DATA_ROW_OTHER, A.LAST_DATA_ROW_OTHER  # 14, 17
    assert formulas.get(f"C{r}") == f"=SUM(C{first}:C{last})"
    assert formulas.get(f"D{r}") == f"=SUM(D{first}:D{last})"


def test_subtotal_current_aje_rje_are_not_external_d44_ref(formulas: dict[str, str]) -> None:
    """反证：本期 AJE/RJE 小计**不是**引用 D4-4 的外部公式（那才是旧前端的错口径）。

    逐行 SUM 里只含本 sheet 的行区间引用；若模板本意是取 D4-4 汇总额，公式会形如
    引用别的 sheet/命名区域。断言它们是 SUM(同列区间) 而非跨表引用。
    """
    for cell in (f"C{A.SUBTOTAL_ROW_MAIN}", f"D{A.SUBTOTAL_ROW_MAIN}",
                 f"C{A.SUBTOTAL_ROW_OTHER}", f"D{A.SUBTOTAL_ROW_OTHER}"):
        f = formulas.get(cell, "")
        assert f.startswith("=SUM("), f"{cell} 非逐行 SUM 口径：{f!r}"
        assert "!" not in f, f"{cell} 含跨表引用（疑似取 D4-4）：{f!r}"
